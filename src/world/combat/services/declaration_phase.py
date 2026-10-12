"""Declaration-phase opening, declaration validators, charge, and NPC target selection."""

from __future__ import annotations

from collections.abc import Callable
import random
from typing import TYPE_CHECKING, TypeVar

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from world.combat.constants import (
    CHARGE_MAX_HOPS,
    ActionCategory,
    CombatManeuver,
    EncounterType,
    OpponentStatus,
    ParticipantStatus,
    SustainedKind,
    TargetingMode,
    TargetSelection,
)
from world.combat.models import (
    CombatEncounter,
    CombatOpponent,
    CombatOpponentAction,
    CombatParticipant,
    CombatRoundAction,
    PendingOpponentAttack,
    SustainedAction,
    ThreatPoolEntry,
)
from world.combat.services.foundations import _ensure_combat_engagement
from world.combat.services.opponents import _dissolve_graduated_bonds, expire_pulls_for_round
from world.fatigue.constants import EffortLevel
from world.scenes.constants import RoundStatus

if TYPE_CHECKING:
    from world.magic.models import Technique


@transaction.atomic
def begin_declaration_phase(encounter: CombatEncounter) -> None:
    """Advance round_number by 1 and set status to DECLARING.

    Uses select_for_update to prevent concurrent calls.
    Raises ValueError if the encounter is not BETWEEN_ROUNDS.
    """
    from world.standoffs.services.state import is_in_standoff  # noqa: PLC0415

    enc = CombatEncounter.objects.select_for_update().get(pk=encounter.pk)
    if is_in_standoff(enc):
        msg = "The standoff has not broken yet."
        raise ValueError(msg)
    if enc.status != RoundStatus.BETWEEN_ROUNDS:
        msg = (
            f"Cannot begin declaration phase: encounter status is "
            f"'{enc.get_status_display()}', expected 'Between Rounds'."
        )
        raise ValueError(msg)

    has_opponents = CombatOpponent.objects.filter(
        encounter=enc,
        status=OpponentStatus.ACTIVE,
    ).exists()
    if not has_opponents:
        msg = "Cannot begin declaration phase: no active opponents in encounter."
        raise ValueError(msg)

    # Belt-and-suspenders: reject a lethal PvP duel before declaration advances.
    if enc.encounter_type == EncounterType.DUEL:
        from world.combat.duels import assert_duel_lethality_valid  # noqa: PLC0415

        assert_duel_lethality_valid(enc)

    enc.round_number += 1
    enc.status = RoundStatus.DECLARING
    enc.round_started_at = timezone.now()
    enc.save(update_fields=["round_number", "status", "round_started_at"])

    # #3567: a new round burns one tick of the running beat's scene clock. The
    # selector resolves the beat; a scene with no running beat or no open clock
    # is a no-op. The fill's completion is scheduled on_commit by the service.
    from world.scenes.clock_services import tick_scene_clock  # noqa: PLC0415

    tick_scene_clock(enc.scene)

    # Reaction economy (#2639): every participant's reaction budget refills
    # each round. A raw queryset .update() would bypass the SharedMemoryModel
    # identity map — any already-cached CombatParticipant instance (e.g. one
    # a caller is still holding) would keep reading its stale pre-reset value
    # forever, since refresh_from_db() on an idmapper model returns the SAME
    # cached instance rather than re-hydrating it from the row. Mutate the
    # identity-mapped instances directly, then persist with one bulk_update
    # query — correct in-memory state AND a single query, not a per-
    # participant save() loop.
    reset_participants = list(CombatParticipant.objects.filter(encounter=enc))
    for reset_participant in reset_participants:
        reset_participant.reactions_used = 0
    if reset_participants:
        CombatParticipant.objects.bulk_update_with_reason(
            reset_participants,
            ["reactions_used"],
            reason="issue #3817: intentional bulk write",
        )

    # --- Round-start per-participant upkeep: DoT tick + engagement ensure ---
    from world.vitals.services import tick_round_for_targets  # noqa: PLC0415

    active_participants_start = CombatParticipant.objects.filter(
        encounter=enc,
        status=ParticipantStatus.ACTIVE,
    ).select_related("character_sheet__character")
    active_opponents_start = CombatOpponent.objects.filter(
        encounter=enc,
        status=OpponentStatus.ACTIVE,
    ).select_related("objectdb")
    start_targets = [p.character_sheet.character for p in active_participants_start]
    start_targets += [opp.objectdb for opp in active_opponents_start if opp.objectdb is not None]
    tick_round_for_targets(start_targets, timing="start")

    for p in active_participants_start:
        # Permanent idempotency safety net: any participant that reached this
        # point without a combat engagement (however they were created) gets
        # one ensured here so all downstream engagement-dependent paths are safe.
        _ensure_combat_engagement(p)

    # --- Escalation tick (#872): opted-in encounters build pressure each round ---
    from world.combat.escalation import (  # noqa: PLC0415
        apply_escalation_tick,
        install_escalation_room_triggers,
    )

    if enc.escalation_curve is not None:
        install_escalation_room_triggers(enc)
        apply_escalation_tick(enc)

    # --- Mentor's Vow (#1165): persist graduated bond dissolution at round start ---
    # Bonds that have graduated (adjusted party leveled into band) are dissolved
    # here so future reads via effective_combat_level skip them cleanly.
    _dissolve_graduated_bonds(enc)

    # Spec A §3.8 + §7.4 lines 2031–2039: expire pulls for the previous
    # round *after* round_number has advanced so the < comparison catches
    # the old rows. recompute_max_health_with_threads runs per affected
    # participant inside expire_pulls_for_round (clamp-not-injure).
    expire_pulls_for_round(enc)
    # Refresh the caller's instance so it reflects the new state.
    encounter.refresh_from_db()


def _validate_no_pending_sustained(
    participant: CombatParticipant, encounter: CombatEncounter
) -> None:
    """Raise if *participant* is still holding a SustainedAction together (#2705, D2).

    Sustaining occupies your action: you cannot hold a ritual together or wind
    up a technique and also declare something new. This is structural, not
    merely thematic — ``CombatRoundAction``'s ``unique_action_per_participant_
    per_round`` constraint means maturation (which clones the declaring action
    into the maturation round) would collide with a same-round declaration if
    this were allowed.

    Filters ``resolves_round__gte`` (not ``__gt``): the round lifecycle is
    DECLARING(R) *then* ``resolve_round(R)`` — a row maturing THIS round is
    NOT yet consumed while declaration is happening, because maturation only
    runs from ``resolve_round``, during RESOLVING. A ``__gt`` filter would
    therefore let a second action be declared for the maturing participant's
    own maturation round; ``update_or_create`` would create a
    ``CombatRoundAction(participant, round_number)`` row, and
    ``_mature_sustained_technique``'s bare ``.objects.create()`` for that same
    ``(participant, round_number)`` would then collide with
    ``unique_action_per_participant_per_round`` and raise an uncaught
    ``IntegrityError`` that aborts ``resolve_round`` for the entire encounter
    (#2705 adversarial review, Fix 1). ``__gte`` closes the gap: a row with
    ``resolves_round == round_number`` blocks declaration exactly like one
    still further out.

    Excludes a TECHNIQUE row with ``declared_round == round_number``: that row
    is THIS round's own in-progress commitment, not a prior one blocking a new
    declaration — a player amending their current round's declaration must
    still reach ``_sync_sustained_technique_declaration``'s delete-then-recreate
    idempotence, never this gate. A RITUAL row is never excluded this way even
    when ``declared_round == round_number``: a ritual is declared through
    ``try_declare_sustained_ritual`` (``PerformRitualAction``), a completely
    different seam from ``declare_action`` — there is no sync step here that
    will replace it, so a same-round ritual commitment must still block a
    combat declaration (Fix 2b; conducting a ritual and swinging a sword in the
    same round is not allowed, D2).
    """
    pending = (
        SustainedAction.objects.filter(
            participant=participant,
            resolves_round__gte=encounter.round_number,
        )
        .exclude(
            declared_round=encounter.round_number,
            sustained_kind=SustainedKind.TECHNIQUE,
        )
        .first()
    )
    if pending is not None:
        msg = f"Cannot declare an action: you are still holding {pending.subject_name} together."
        raise ValueError(msg)


def _validate_passive_slot(
    focused_category: str | None,
    *,
    physical_passive: Technique | None,
    social_passive: Technique | None,
    mental_passive: Technique | None,
) -> None:
    """Raise if the passive slot matching ``focused_category`` is occupied."""
    if focused_category is None:
        return
    passive_map = {
        ActionCategory.PHYSICAL: physical_passive,
        ActionCategory.SOCIAL: social_passive,
        ActionCategory.MENTAL: mental_passive,
    }
    if passive_map.get(focused_category) is not None:
        msg = (
            f"Cannot declare action: {focused_category} passive must be "
            f"None when focused_category is {focused_category}."
        )
        raise ValueError(msg)


def _supplied_target_kind(
    participant: CombatParticipant,
    focused_ally_target: CombatParticipant | None,
    focused_opponent_target: CombatOpponent | None,
) -> object | None:
    """Map the supplied target to its ConditionTargetKind, or None if no target."""
    from world.magic.models.techniques import ConditionTargetKind  # noqa: PLC0415

    if focused_ally_target is not None:
        if focused_ally_target == participant:
            return ConditionTargetKind.SELF
        return ConditionTargetKind.ALLY
    if focused_opponent_target is not None:
        return ConditionTargetKind.ENEMY
    return None


def _validate_target_kind_alignment(
    participant: CombatParticipant,
    focused_action: Technique,
    focused_ally_target: CombatParticipant | None,
    focused_opponent_target: CombatOpponent | None,
) -> None:
    """Raise if the supplied target's kind is not accepted by the technique."""
    from world.magic.models.techniques import ConditionTargetKind  # noqa: PLC0415

    rows = list(focused_action.condition_applications.all())
    has_base_power = focused_action.effect_type.base_power is not None

    if rows:
        kinds = {row.target_kind for row in rows}
        target_supplied_kind = _supplied_target_kind(
            participant, focused_ally_target, focused_opponent_target
        )
        # Accept SELF/ALLY interchangeably for ally-targets
        accepted = kinds.copy()
        if ConditionTargetKind.ALLY in accepted:
            accepted.add(ConditionTargetKind.SELF)
        if ConditionTargetKind.SELF in accepted:
            accepted.add(ConditionTargetKind.ALLY)
        if target_supplied_kind is not None and target_supplied_kind not in accepted:
            msg = (
                f"Technique target_kinds {sorted(kinds)} do not match supplied "
                f"target kind '{target_supplied_kind}'."
            )
            raise ValueError(msg)

    if has_base_power and not rows and focused_opponent_target is None:
        msg = "Damage technique requires focused_opponent_target."
        raise ValueError(msg)


def _validate_technique_reach(
    participant: CombatParticipant,
    focused_action: Technique,
    *,
    focused_opponent_target: CombatOpponent | None,
    focused_ally_target: CombatParticipant | None,
) -> None:
    """Raise ValueError if the technique's reach cannot cover the declared target.

    Resolves the target's ObjectDB from either ``focused_opponent_target.objectdb``
    (for NPC/opponent targets) or ``focused_ally_target.character_sheet.character``
    (for participant/ally targets). Delegates to ``technique_can_reach``, which is
    lenient when either combatant is unpositioned.

    Only runs when a target is actually provided; skips self/no-target declarations.
    """
    from world.combat.reach import technique_can_reach  # noqa: PLC0415

    attacker_objectdb = participant.character_sheet.character

    target_objectdb = None
    if focused_opponent_target is not None:
        target_objectdb = focused_opponent_target.objectdb
    elif focused_ally_target is not None and focused_ally_target != participant:
        target_objectdb = focused_ally_target.character_sheet.character

    if target_objectdb is None:
        # No external target (self-buff or no target) — reach is not constraining.
        return

    if not technique_can_reach(attacker_objectdb, focused_action, target_objectdb):
        from actions.errors import ActionDispatchError  # noqa: PLC0415

        raise ActionDispatchError(ActionDispatchError.TARGET_OUT_OF_REACH)


def _validate_strain_commitment(participant: CombatParticipant, strain_commitment: int) -> None:
    """Reject a strain overcommit beyond the participant's anima budget (#3446).

    The push-yourself lever is capped by the same budget the clash UI reads
    (mirrors ``_cap_strain_by_anima`` on the standalone cast serializer).
    Negative values are a caller bug, not a player choice.
    """
    if strain_commitment < 0:
        msg = "Strain commitment cannot be negative."
        raise ValueError(msg)
    if strain_commitment > participant.available_strain:
        msg = (
            f"Strain commitment ({strain_commitment}) exceeds available "
            f"anima ({participant.available_strain})."
        )
        raise ValueError(msg)


def declare_charge(
    participant: CombatParticipant,
    technique: Technique,
    opponent: CombatOpponent,
) -> CombatRoundAction:
    """Declare a mounted charge — closes distance to *opponent*, then attacks (#1843).

    Validations:
    - Participant must be able to act and the encounter must be DECLARING.
    - The rider must hold the Mounted condition
      (``world.companions.mount_content.MOUNTED_CONDITION_NAME``).
    - *opponent* must be ACTIVE.
    - *opponent*'s position must be at least 1 hop from the rider's current
      position AND reachable within ``CHARGE_MAX_HOPS``. Lenient (allowed)
      when either combatant is unpositioned — mirrors
      ``technique_can_reach``'s leniency (``world/combat/reach.py``).

    Resolution (``_resolve_pc_action``) moves the rider onto *opponent*'s
    position (``force_move_to_position``), then falls through to the normal
    weapon-attack pipeline — ``CombatTechniqueResolver`` folds
    ``CHARGE_CHECK_BONUS``/``CHARGE_DAMAGE_BONUS`` into the check/damage
    (doubled when the equipped weapon is a LANCE). The attack always runs
    through the normal (non-bypassing) damage pipeline — defenses, guardians,
    and ramparts fire exactly as they would for any other attack.

    Raises ValueError with clear messages for validation failures.
    """
    from world.areas.positioning.services import position_of, position_reachable  # noqa: PLC0415
    from world.companions.mount_content import MOUNTED_CONDITION_NAME  # noqa: PLC0415
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.conditions.services import has_condition  # noqa: PLC0415
    from world.magic.constants import TechniqueReach  # noqa: PLC0415
    from world.vitals.services import can_act  # noqa: PLC0415

    encounter = participant.encounter
    if not can_act(participant.character_sheet):
        msg = "Cannot charge: character is dead or incapacitated."
        raise ValueError(msg)
    if encounter.status != RoundStatus.DECLARING:
        msg = (
            f"Cannot charge: encounter status is "
            f"'{encounter.get_status_display()}', expected 'Declaring'."
        )
        raise ValueError(msg)
    if opponent.status != OpponentStatus.ACTIVE:
        msg = "Cannot charge a defeated opponent."
        raise ValueError(msg)

    mounted_template = ConditionTemplate.get_by_name(MOUNTED_CONDITION_NAME)
    if not has_condition(participant.character_sheet.character, mounted_template):
        msg = "Cannot charge: you must be mounted."
        raise ValueError(msg)

    rider_pos = position_of(participant.character_sheet.character)
    target_pos = position_of(opponent.objectdb) if opponent.objectdb is not None else None
    if rider_pos is not None and target_pos is not None:
        if rider_pos.pk == target_pos.pk:
            msg = "Cannot charge: the target is already within reach."
            raise ValueError(msg)
        if not position_reachable(
            rider_pos, target_pos, TechniqueReach.REACH_N, reach_hops=CHARGE_MAX_HOPS
        ):
            msg = "Cannot charge: the target is not reachable."
            raise ValueError(msg)

    action, _created = CombatRoundAction.objects.update_or_create(
        participant=participant,
        round_number=encounter.round_number,
        defaults={
            "focused_action": technique,
            "focused_category": technique.action_category,
            "effort_level": EffortLevel.MEDIUM,
            "focused_opponent_target": opponent,
            "focused_ally_target": None,
            "maneuver": CombatManeuver.CHARGE,
            "physical_passive": None,
            "social_passive": None,
            "mental_passive": None,
            "combo_upgrade": None,
            "is_ready": False,
        },
    )
    return action


_JOUST_PARTICIPANT_COUNT = 2  # jousts are strictly 1v1 DUEL encounters


def _get_eligible_entries(
    opponent: CombatOpponent,
    entries: list[ThreatPoolEntry],
    cooldown_used_entry_ids: set[int],
) -> list[ThreatPoolEntry]:
    """Return threat pool entries eligible for this opponent's current state.

    Args:
        opponent: The opponent selecting an action.
        entries: Pre-fetched threat pool entries for this opponent's pool.
        cooldown_used_entry_ids: Entry IDs recently used (within cooldown window)
            by this opponent. Pre-fetched in batch by the caller.
    """
    eligible: list[ThreatPoolEntry] = []
    # Falter: skip entries that require a steady nerve (#2015).
    from world.combat.morale import (  # noqa: PLC0415
        OpponentMoraleState,
        morale_state_for,
    )

    faltering = morale_state_for(opponent) == OpponentMoraleState.FALTER

    for entry in entries:
        # Falter: skip requires_steady entries (designers author "weakened" entries).
        if faltering and entry.requires_steady:
            continue

        # Filter by minimum_phase
        if entry.minimum_phase is not None and entry.minimum_phase > opponent.current_phase:
            continue

        # Filter by cooldown — check against pre-fetched set
        if entry.cooldown_rounds is not None and entry.pk in cooldown_used_entry_ids:
            continue

        eligible.append(entry)

    return eligible


_TargetT = TypeVar("_TargetT")


def _select_targets_core(
    entry: ThreatPoolEntry,
    candidates: list[_TargetT],
    health_of: Callable[[list[_TargetT]], list[int]],
    rotation: int = 0,
    *,
    _threat_map: dict[int, int] | None = None,
    _shield_participant_ids: set[int] | None = None,
) -> list[_TargetT]:
    """Shared targeting-mode selector for participants and opponents (#1584).

    One algorithm (ALL / MULTI / RANDOM / LOWEST_HEALTH / HIGHEST_THREAT /
    SPECIFIC_ROLE / rotated-default) drives both the participant ``targets``
    path and the opponent ``opponent_targets`` path (ADR-0016 — no parallel
    selector).

    ``health_of`` returns health values parallel to ``candidates`` and is only
    invoked for the LOWEST_HEALTH mode, so participants keep their single batch
    query and opponents read ``.health`` directly.

    ``_threat_map`` and ``_shield_participant_ids`` are pre-computed by
    ``select_npc_actions`` for HIGHEST_THREAT / SPECIFIC_ROLE modes (#2020).
    They map candidate PKs to threat values and identify SHIELD-axis PCs (blend
    weight > 0).

    ``rotation`` offsets the deterministic (non-random, non-health-sorted)
    selection so a swarm's successive attacks fan across distinct targets rather
    than dogpiling the first one (#983). It is a no-op for the ALL, RANDOM, and
    LOWEST_HEALTH modes, which already spread across or intentionally focus on
    their own terms.
    """
    if not candidates:
        return []

    mode = entry.targeting_mode
    selection = entry.target_selection

    if mode == TargetingMode.ALL:
        return list(candidates)

    count = 1
    if mode == TargetingMode.MULTI:
        count = entry.target_count or 1

    count = min(count, len(candidates))

    if selection == TargetSelection.LOWEST_HEALTH:
        healths = health_of(candidates)
        sorted_by_health = [
            c
            for _, c in sorted(
                zip(healths, candidates, strict=True),
                key=lambda pair: pair[0],
            )
        ]
        return sorted_by_health[:count]

    if selection == TargetSelection.RANDOM:
        return random.sample(candidates, count)  # NOSONAR game RNG (combat targeting), not crypto

    # HIGHEST_THREAT: sort candidates by ThreatRecord.threat_value desc (#2020).
    # Falls back to rotated order when no threat records exist (pre-threat
    # encounters or mooks with no damage yet).
    if selection == TargetSelection.HIGHEST_THREAT and _threat_map:
        sorted_by_threat = sorted(
            candidates,
            key=lambda c: _threat_map.get(c.pk, 0),
            reverse=True,
        )
        return sorted_by_threat[:count]

    # SPECIFIC_ROLE: prioritize SHIELD-axis (defense) PCs, then break ties
    # by highest threat (#2020). Falls back to highest-threat-only (or rotated)
    # when no SHIELD-axis PC is present.
    if selection == TargetSelection.SPECIFIC_ROLE and _shield_participant_ids:
        shielded = [c for c in candidates if c.pk in _shield_participant_ids]
        if shielded:
            if _threat_map:
                shielded.sort(
                    key=lambda c: _threat_map.get(c.pk, 0),
                    reverse=True,
                )
            return shielded[:count]

    # Default: rotated DB order (no threat data available).
    offset = rotation % len(candidates)
    rotated = candidates[offset:] + candidates[:offset]
    return list(rotated[:count])


def _select_targets(
    entry: ThreatPoolEntry,
    active_participants: list[CombatParticipant],
    rotation: int = 0,
    *,
    _threat_map: dict[int, int] | None = None,
    _shield_participant_ids: set[int] | None = None,
) -> list[CombatParticipant]:
    """Select participant targets for a threat pool entry (typed wrapper)."""

    def _participant_healths(candidates: list[CombatParticipant]) -> list[int]:
        from world.vitals.models import CharacterVitals  # noqa: PLC0415

        sheet_ids = [p.character_sheet_id for p in candidates]
        health_map = dict(
            CharacterVitals.objects.filter(
                character_sheet_id__in=sheet_ids,
            ).values_list("character_sheet_id", "health")
        )
        return [health_map.get(p.character_sheet_id, 0) for p in candidates]

    return _select_targets_core(
        entry,
        active_participants,
        _participant_healths,
        rotation,
        _threat_map=_threat_map,
        _shield_participant_ids=_shield_participant_ids,
    )


def _select_opponent_targets(
    entry: ThreatPoolEntry,
    active_opponents: list[CombatOpponent],
    rotation: int = 0,
    *,
    _threat_map: dict[int, int] | None = None,
    _shield_participant_ids: set[int] | None = None,
) -> list[CombatOpponent]:
    """Select opponent targets for a threat pool entry (typed wrapper, #1584).

    Routes an ALLY summon's attack at ENEMY opponents; opponents carry health on
    the row, so no batch query is needed.
    """
    return _select_targets_core(
        entry,
        active_opponents,
        lambda opps: [o.health for o in opps],
        rotation,
        _threat_map=_threat_map,
        _shield_participant_ids=_shield_participant_ids,
    )


def _build_cooldown_q_filters(
    opponents: list[CombatOpponent],
    entries_by_pool: dict[int, list[ThreatPoolEntry]],
    round_number: int,
) -> tuple[Q, Q]:
    """Build OR-ed Q filters for committed and pending cooldown entries.

    Iterates opponents, collecting per-pool cooldown entry IDs and computing
    the earliest allowed round for each, then OR-combines into two Q objects.

    Args:
        opponents: The opponents to build filters for.
        entries_by_pool: Mapping of threat_pool_id to entries.
        round_number: The current round number.

    Returns:
        A tuple of ``(cooldown_filters, pending_cooldown_filters)`` — both empty
        ``Q()`` when no opponent has cooldown entries.
    """
    cooldown_filters = Q()
    pending_cooldown_filters = Q()
    for opponent in opponents:
        opp_entries = entries_by_pool.get(opponent.threat_pool_id, [])
        cooldown_entry_ids = [e.pk for e in opp_entries if e.cooldown_rounds is not None]
        if not cooldown_entry_ids:
            continue
        max_cooldown = max(e.cooldown_rounds for e in opp_entries if e.cooldown_rounds is not None)
        earliest_allowed = max(1, round_number - max_cooldown + 1)
        cooldown_filters |= Q(
            opponent=opponent,
            threat_entry_id__in=cooldown_entry_ids,
            round_number__gte=earliest_allowed,
        )
        pending_cooldown_filters |= Q(
            opponent=opponent,
            threat_entry_id__in=cooldown_entry_ids,
            declared_round__gte=earliest_allowed,
        )
    return cooldown_filters, pending_cooldown_filters


def _collect_cooldown_actions(
    cooldown_filters: Q,
    entry_cooldown_map: dict[int, int],
    round_number: int,
    result: dict[int, set[int]],
) -> dict[int, set[int]]:
    """Collect committed-action cooldown hits into *result*.

    Args:
        cooldown_filters: OR-ed Q filter for ``CombatOpponentAction``.
        entry_cooldown_map: Mapping of entry_id to cooldown_rounds.
        round_number: The current round number.
        result: Accumulating result dict (mutated in place).

    Returns:
        The mutated *result* dict.
    """
    recent_actions = CombatOpponentAction.objects.filter(cooldown_filters).values_list(
        "opponent_id", "threat_entry_id", "round_number"
    )
    for opp_id, entry_id, round_num in recent_actions:
        cooldown = entry_cooldown_map.get(entry_id)
        if cooldown is not None:
            earliest = max(1, round_number - cooldown + 1)
            if round_num >= earliest:
                result[opp_id].add(entry_id)
    return result


def _collect_cooldown_pending(
    pending_cooldown_filters: Q,
    entry_cooldown_map: dict[int, int],
    round_number: int,
    result: dict[int, set[int]],
) -> dict[int, set[int]]:
    """Collect pending-windup cooldown hits into *result*.

    Args:
        pending_cooldown_filters: OR-ed Q filter for ``PendingOpponentAttack``.
        entry_cooldown_map: Mapping of entry_id to cooldown_rounds.
        round_number: The current round number.
        result: Accumulating result dict (mutated in place).

    Returns:
        The mutated *result* dict.
    """
    recent_pending = PendingOpponentAttack.objects.filter(pending_cooldown_filters).values_list(
        "opponent_id", "threat_entry_id", "declared_round"
    )
    for opp_id, entry_id, round_num in recent_pending:
        cooldown = entry_cooldown_map.get(entry_id)
        if cooldown is not None:
            earliest = max(1, round_number - cooldown + 1)
            if round_num >= earliest:
                result[opp_id].add(entry_id)
    return result
