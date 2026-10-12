"""The declare_action entry point, sustained rituals, and NPC companion orders."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any

from django.db.models import Q

from world.combat import services as _svc
from world.combat.constants import (
    SUSTAINED_GENERIC_TELEGRAPH,
    WINDUP_GENERIC_TELEGRAPH,
    WINDUP_NO_TARGET_LABEL,
    WINDUP_TARGET_CLAUSE,
    CombatAllegiance,
    EncounterType,
    OpponentStatus,
    ParticipantStatus,
    SustainedKind,
)
from world.combat.models import (
    CombatEncounter,
    CombatOpponent,
    CombatOpponentAction,
    CombatParticipant,
    CombatRoundAction,
    EncounterRiskAcknowledgement,
    PendingOpponentAttack,
    SustainedAction,
    ThreatPoolEntry,
)
from world.combat.services.declaration_phase import (
    _build_cooldown_q_filters,
    _collect_cooldown_actions,
    _collect_cooldown_pending,
    _select_opponent_targets,
    _select_targets,
    _validate_no_pending_sustained,
    _validate_passive_slot,
    _validate_strain_commitment,
    _validate_target_kind_alignment,
    _validate_technique_reach,
)
from world.combat.services.foundations import (
    combatants_hostile_to,
    roll_sustained_absorption_budget,
)
from world.conditions.constants import Allegiance
from world.scenes.constants import RoundStatus

if TYPE_CHECKING:
    from world.areas.positioning.models import Position
    from world.character_sheets.models import CharacterSheet
    from world.magic.models import FuryTier, Ritual, Technique


def declare_action(  # noqa: PLR0913 - action declaration requires all slot fields
    participant: CombatParticipant,
    *,
    focused_action: Technique | None = None,
    focused_category: str | None = None,
    effort_level: str,
    focused_opponent_target: CombatOpponent | None = None,
    focused_ally_target: CombatParticipant | None = None,
    physical_passive: Technique | None = None,
    social_passive: Technique | None = None,
    mental_passive: Technique | None = None,
    confirm_soulfray_risk: bool = False,
    strain_commitment: int = 0,
    fury_commitment: FuryTier | None = None,
    fury_anchor: CharacterSheet | None = None,
    cast_destination: Position | None = None,
    cast_position_a: Position | None = None,
    cast_position_b: Position | None = None,
) -> CombatRoundAction:
    """Declare a PC's action for the current round.

    Validations:
    - Participant must be able to act (not dead and not incapacitated) — see can_act.
      A dying-but-conscious character keeps awareness and passes naturally.
    - Encounter must be in DECLARING status.
    - Round number must match encounter's current round.
    - The passive slot matching the focused_category must be None.
    - focused_opponent_target and focused_ally_target are mutually exclusive.
    - focused_action's condition_applications target_kinds must match the supplied target.
    - A pure-damage technique (base_power, no condition rows) requires focused_opponent_target.

    ``cast_destination``/``cast_position_a``/``cast_position_b`` are pre-validated
    (see ``resolve_cast_position_params``, #2206) — this function only persists them.

    Raises ValueError with clear messages for validation failures.
    """

    from world.vitals.services import can_act  # noqa: PLC0415

    encounter = participant.encounter

    # The focused technique's authored category is authoritative (#614): it drives
    # which passive slot must stay empty. Override any client-supplied value.
    if focused_action is not None:
        focused_category = focused_action.action_category

    # Agency check — not dead and not incapacitated. A dying-but-conscious
    # character keeps awareness and passes naturally (no dying_final_round concept).
    if not can_act(participant.character_sheet):
        msg = "Cannot declare action: character is dead or incapacitated."
        raise ValueError(msg)

    _validate_strain_commitment(participant, strain_commitment)

    # Encounter status check
    if encounter.status != RoundStatus.DECLARING:
        msg = (
            f"Cannot declare action: encounter status is "
            f"'{encounter.get_status_display()}', expected 'Declaring'."
        )
        raise ValueError(msg)

    # Lethal-duel risk-acknowledgement gate (#568 Task 12b). A PC placed into a
    # lethal DUEL by create_lethal_duel is deliberately not auto-acknowledged, and
    # the #777 outsider gate does not cover an already-active participant — so block
    # declaration until an EncounterRiskAcknowledgement exists. Scoped to DUEL only:
    # lethal party-combat PCs self-join via join_encounter (which records an ack),
    # and GM-placed party-combat PCs (add_participant, no ack) must not be blocked.
    if encounter.encounter_type == EncounterType.DUEL and encounter.is_lethal:
        has_ack = EncounterRiskAcknowledgement.objects.filter(
            encounter=encounter,
            character_sheet=participant.character_sheet,
        ).exists()
        if not has_ack:
            msg = "You must acknowledge the lethal risk of this duel before acting."
            raise ValueError(msg)

    # Sustaining occupies your action (#2705, D2) — see _validate_no_pending_sustained.
    _validate_no_pending_sustained(participant, encounter)

    # Passive slot validation (only when a focused category is declared)
    _validate_passive_slot(
        focused_category,
        physical_passive=physical_passive,
        social_passive=social_passive,
        mental_passive=mental_passive,
    )

    if focused_opponent_target and focused_opponent_target.status != OpponentStatus.ACTIVE:
        msg = "Cannot target a defeated opponent."
        raise ValueError(msg)

    # XOR target validation
    if focused_opponent_target and focused_ally_target:
        msg = "Action cannot target both an opponent and an ally."
        raise ValueError(msg)

    # Target-kind alignment with technique authoring
    if focused_action is not None:
        _validate_target_kind_alignment(
            participant,
            focused_action,
            focused_ally_target,
            focused_opponent_target,
        )

    # Positional reach gate: enforce technique.reach against the declared target.
    # Only fires when there is a technique and a resolved target. Lenient when
    # either combatant is unpositioned (technique_can_reach returns True).
    if focused_action is not None:
        _validate_technique_reach(
            participant,
            focused_action,
            focused_opponent_target=focused_opponent_target,
            focused_ally_target=focused_ally_target,
        )

    action, _created = CombatRoundAction.objects.update_or_create(
        participant=participant,
        round_number=encounter.round_number,
        defaults={
            "focused_action": focused_action,
            "focused_category": focused_category,
            "effort_level": effort_level,
            "focused_opponent_target": focused_opponent_target,
            "focused_ally_target": focused_ally_target,
            "physical_passive": physical_passive,
            "social_passive": social_passive,
            "mental_passive": mental_passive,
            "maneuver": None,  # Reset maneuver on re-declaration
            "combo_upgrade": None,  # Reset combo on re-declaration
            "is_ready": False,  # Reset ready on re-declaration
            "confirm_soulfray_risk": confirm_soulfray_risk,
            "strain_commitment": strain_commitment,
            "fury_commitment": fury_commitment,
            "fury_anchor": fury_anchor,
            "cast_destination": cast_destination,
            "cast_position_a": cast_position_a,
            "cast_position_b": cast_position_b,
        },
    )

    _sync_sustained_technique_declaration(participant, action, focused_action)

    return action


def _sync_sustained_technique_declaration(
    participant: CombatParticipant,
    action: CombatRoundAction,
    technique: Technique | None,
) -> SustainedAction | None:
    """Create (or clear) this round's SustainedAction commitment for *technique* (#2705).

    Called unconditionally from ``declare_action`` (no branch there — keeps its
    cyclomatic complexity down) so re-declaration is always synced: any
    existing TECHNIQUE-kind SustainedAction for ``(participant, declared_round=
    encounter.round_number)`` is deleted first — a player re-declaring the same
    round's action, whether to the same winding-up technique or to something
    else entirely, must never stack a second row — and a new one is created
    only when ``technique`` is set and ``technique.windup_rounds > 0``. Rolls
    Concentration once (via ``roll_sustained_absorption_budget``) each time a
    commitment is (re-)declared.

    Scoped to ``sustained_kind=SustainedKind.TECHNIQUE`` (#2705 adversarial
    review, Fix 2a): a RITUAL row for the same ``(participant, declared_round)``
    is created through a completely different seam
    (``try_declare_sustained_ritual``, called from ``PerformRitualAction`` —
    never from ``declare_action``), and its components were already consumed
    at declaration. An unscoped delete here would silently strand a sustained
    ritual's already-consumed components the moment the player declared
    anything else that same round — no narration, no refund, the commitment
    simply vanishes. ``_validate_no_pending_sustained`` (called earlier in
    ``declare_action``) now blocks that combat declaration outright while a
    RITUAL commitment is pending (Fix 2b), so in practice this delete should
    never even see a RITUAL row for this participant — but scoping it
    correctly here is the actual fix; the validation is defense in depth.
    """
    encounter = participant.encounter
    SustainedAction.objects.filter(
        participant=participant,
        declared_round=encounter.round_number,
        sustained_kind=SustainedKind.TECHNIQUE,
    ).delete()

    if technique is None or technique.windup_rounds <= 0:
        return None

    budget, outcome = roll_sustained_absorption_budget(participant)
    sustained = SustainedAction.objects.create(
        encounter=encounter,
        participant=participant,
        sustained_kind=SustainedKind.TECHNIQUE,
        technique=technique,
        declared_action=action,
        declared_round=encounter.round_number,
        resolves_round=encounter.round_number + technique.windup_rounds,
        absorption_budget=budget,
        outcome_snapshot=outcome,
    )
    _broadcast_sustained_telegraph(sustained)
    return sustained


def try_declare_sustained_ritual(
    *,
    sheet: CharacterSheet,
    ritual: Ritual,
    kwargs: dict[str, Any],
) -> SustainedAction | None:
    """Defer a combat-cast ritual across rounds instead of dispatching now (#2705, Task 5).

    Called by ``PerformRitualAction.execute()`` after components are validated
    and consumed (so a broken commitment is genuinely spent — components are
    never refunded, mirroring ``_mature_one_sustained_action``'s TECHNIQUE
    ruling) and before dispatch. Returns ``None`` — "not sustained, dispatch
    immediately as today" — unless ALL of the following hold:

    - the performer resolves to an ACTIVE ``CombatParticipant`` whose
      encounter is currently DECLARING;
    - ``ritual.check_config_or_none`` is not ``None`` and its
      ``sustained_rounds > 0``;
    - ``kwargs`` is empty (see below);
    - the participant is not already holding an earlier-round commitment —
      mirrors ``_validate_no_pending_sustained``'s D2 guard
      (``declared_round < round_number``, ``resolves_round >= round_number``).
      Unlike that function this does not raise: a ritual invocation is not
      the round-declaration seam, so blocking it outright would strand the
      components already consumed inside the same atomic transaction. Instead
      it falls through to immediate dispatch, same as any other inert case —
      a player cannot stack two parallel sustained commitments, but a ritual
      cast while one is already pending simply isn't deferred.

    **The ADR-0007 kwargs guard.** A ``SustainedAction`` is a DB row with
    fixed columns; persisting an arbitrary per-cast kwargs dict to replay at
    maturation would need a JSON field, which ADR-0007 forbids. A ritual
    invoked with non-empty kwargs (e.g. a ``thread`` target) therefore cannot
    be deferred — it dispatches immediately, exactly as it would outside
    combat. Rituals authored with ``sustained_rounds > 0`` are expected to be
    no-kwargs SERVICE/FLOW calls for this reason.

    When it fires: rolls the absorption budget once
    (``roll_sustained_absorption_budget``, the same helper the TECHNIQUE
    declaration path uses), creates the ``SustainedAction`` (kind RITUAL,
    ``declared_action=None`` — a ritual is declared through
    ``PerformRitualAction``, not the combat round-declaration seam),
    broadcasts the telegraph, and returns the row. Same same-round-
    replacement idempotence as ``_sync_sustained_technique_declaration``: any
    existing ``SustainedAction`` for ``(participant, declared_round=this
    round)`` is replaced, never stacked, so re-performing the ritual the same
    round does not accumulate duplicate commitments.
    """
    if kwargs:
        return None

    check_config = ritual.check_config_or_none
    if check_config is None or check_config.sustained_rounds <= 0:
        return None

    participant = (
        CombatParticipant.objects.filter(
            character_sheet=sheet,
            status=ParticipantStatus.ACTIVE,
        )
        .select_related("encounter")
        .first()
    )
    if participant is None:
        return None

    encounter = participant.encounter
    if encounter.status != RoundStatus.DECLARING:
        return None

    # ``resolves_round__gte``, not ``__gt``: a commitment maturing THIS round is
    # still being held during DECLARING — ``resolve_round`` has not run yet, so
    # it has not matured. With ``__gt`` a player could stack a second live
    # commitment on their own maturation round, which the "cannot stack two
    # parallel commitments" invariant below forbids. Same off-by-one that made
    # ``_validate_no_pending_sustained`` crash ``resolve_round``.
    already_holding = SustainedAction.objects.filter(
        participant=participant,
        declared_round__lt=encounter.round_number,
        resolves_round__gte=encounter.round_number,
    ).exists()
    if already_holding:
        return None

    SustainedAction.objects.filter(
        participant=participant, declared_round=encounter.round_number
    ).delete()

    budget, outcome = roll_sustained_absorption_budget(participant)
    sustained = SustainedAction.objects.create(
        encounter=encounter,
        participant=participant,
        sustained_kind=SustainedKind.RITUAL,
        ritual=ritual,
        declared_action=None,
        declared_round=encounter.round_number,
        resolves_round=encounter.round_number + check_config.sustained_rounds,
        absorption_budget=budget,
        outcome_snapshot=outcome,
    )
    _broadcast_sustained_telegraph(sustained)
    return sustained


def _batch_fetch_cooldown_data(
    opponents: list[CombatOpponent],
    entries_by_pool: dict[int, list[ThreatPoolEntry]],
    all_entries: list[ThreatPoolEntry],
    round_number: int,
) -> dict[int, set[int]]:
    """Batch-fetch recently-used entry IDs per opponent for cooldown checks.

    Returns a mapping of opponent_id -> set of entry IDs that are on cooldown.

    #2637: a wind-up entry is committed at DECLARATION, not maturation — it
    does not get a CombatOpponentAction row until it matures rounds later, so
    a pending PendingOpponentAttack's declared_round also counts as "used"
    for cooldown purposes. Batched identically to the CombatOpponentAction
    read below (one extra fixed query, never a query per opponent).
    """
    cooldown_filters, pending_cooldown_filters = _build_cooldown_q_filters(
        opponents, entries_by_pool, round_number
    )

    result: dict[int, set[int]] = defaultdict(set)
    if not cooldown_filters:
        return result

    entry_cooldown_map = {
        e.pk: e.cooldown_rounds for e in all_entries if e.cooldown_rounds is not None
    }

    _collect_cooldown_actions(cooldown_filters, entry_cooldown_map, round_number, result)
    _collect_cooldown_pending(pending_cooldown_filters, entry_cooldown_map, round_number, result)

    return result


def _get_companion_order(opponent: CombatOpponent, round_number: int) -> object | None:
    """Fetch the CompanionOrder for an ALLY summon this round, if any (#1921).

    Returns None for non-summons or when no order exists.
    """
    if opponent.summoned_by_id is None or opponent.allegiance != CombatAllegiance.ALLY:
        return None

    from world.companions.models import Companion, CompanionOrder  # noqa: PLC0415

    try:
        companion = Companion.objects.get(
            owner_id=opponent.summoned_by_id,
            released_at__isnull=True,
        )
    except (Companion.DoesNotExist, Companion.MultipleObjectsReturned):
        return None

    return CompanionOrder.objects.filter(
        companion=companion,
        encounter=opponent.encounter,
        round_number=round_number,
    ).first()


# Sentinel for the HOLD companion order — distinct from ``None`` (no order) and
# from a directed target list (ATTACK_TARGET) so the caller can branch cleanly.
_COMPANION_HOLD = object()


def _apply_companion_order(
    opponent: CombatOpponent,
    round_number: int,
    target_pool: list,
) -> list | object | None:
    """Apply a companion order to narrow or skip the opponent's target pool.

    A HOLD order returns ``_COMPANION_HOLD`` (skip this round). An ATTACK_TARGET
    order narrows *target_pool* to the directed opponent if still alive, and
    returns that list. Returns ``None`` when no companion order is active, when
    the order doesn't match, or when the directed target is dead/gone (fall back
    to auto-selection).

    Args:
        opponent: The ``CombatOpponent`` to check for a companion order.
        round_number: The current round number.
        target_pool: The current target pool (used for ATTACK_TARGET narrowing).

    Returns:
        ``_COMPANION_HOLD`` when the order is HOLD (skip), a narrowed target list
        when the order is ATTACK_TARGET and the target is alive, or ``None`` when
        no companion order applies or the directed target is gone.
    """
    companion_order = _get_companion_order(opponent, round_number)
    if companion_order is None:
        return None

    from world.companions.constants import CompanionOrderKind  # noqa: PLC0415

    if companion_order.order_kind == CompanionOrderKind.HOLD:
        return _COMPANION_HOLD

    if (
        companion_order.order_kind == CompanionOrderKind.ATTACK_TARGET
        and companion_order.target_opponent_id is not None
    ):
        directed = [opp for opp in target_pool if opp.pk == companion_order.target_opponent_id]
        if directed:
            return directed
    return None


def _npc_action_target_pool(
    opponent: CombatOpponent,
    active_participants: list[CombatParticipant],
    encounter: CombatEncounter,  # noqa: ARG001 - kept for caller signature symmetry
    *,
    allegiances: dict[int, Allegiance],
    active_opponents: list[CombatOpponent],
) -> tuple[list, bool]:
    """Route an opponent's targeting by EFFECTIVE allegiance (#1584, #1590, #4091).

    * **ALLY_OF_CASTER** (a #1584 ALLY summon, or a charmed NPC) targets
      ``combatants_hostile_to``'s opponent pool — ACTIVE opponents whose
      effective allegiance is ENEMY or TURNED — minus untargetable
      (intangible) opponents; never a PC.
    * **TURNED** targets other ACTIVE opponents still on its former
      (stored-ENEMY, effectively ENEMY) side; never a PC, never itself.
    * **NEUTRAL** (calmed) skips the round: empty opponent pool.
    * **ENEMY** (the common case) targets the PC side as today — enemies
      ignore charmed/turned NPCs (Decision 3).

    ``active_participants`` is already intangibility- and can_act-filtered by
    ``select_npc_actions``.

    Returns ``(target_pool, targeting_participants)``.
    """
    side = allegiances.get(opponent.pk, Allegiance.ENEMY)
    if side in (Allegiance.ALLY_OF_CASTER, Allegiance.TURNED):
        from world.conditions.services import is_untargetable  # noqa: PLC0415

        opponent_pool = [
            opp
            for opp in combatants_hostile_to(
                opponent, allegiances=allegiances, opponents=active_opponents
            )["opponents"]
            if opp.objectdb_id is None or not is_untargetable(opp.objectdb)
        ]
        return opponent_pool, False
    if side == Allegiance.NEUTRAL:
        return [], True
    return list(active_participants), True


def _set_npc_action_targets(  # noqa: PLR0913
    action: CombatOpponentAction,
    entry: ThreatPoolEntry,
    target_pool: list,
    *,
    targeting_participants: bool,
    rotation: int,
    threat_map: dict[int, int] | None = None,
    shield_participant_ids: set[int] | None = None,
) -> None:
    """Populate exactly one target relation on an NPC action (#1584).

    The opponent branch (an ALLY/charmed/turned attacker, #4091) never forwards
    ``threat_map``/``shield_participant_ids`` — both are pre-computed keyed by
    CombatParticipant pk, and a CombatOpponent pk can collide with one of those
    keys (they are independent sequences), silently corrupting HIGHEST_THREAT /
    SPECIFIC_ROLE selection for opponent targets.
    """
    if targeting_participants:
        action.targets.set(
            _select_targets(
                entry,
                target_pool,
                rotation=rotation,
                _threat_map=threat_map,
                _shield_participant_ids=shield_participant_ids,
            )
        )
    else:
        action.opponent_targets.set(
            _select_opponent_targets(
                entry,
                target_pool,
                rotation=rotation,
                _threat_map=None,
                _shield_participant_ids=None,
            )
        )


def _select_windup_targets(  # noqa: PLR0913
    entry: ThreatPoolEntry,
    target_pool: list,
    *,
    targeting_participants: bool,
    rotation: int,
    threat_map: dict[int, int] | None = None,
    shield_participant_ids: set[int] | None = None,
) -> list:
    """Same selection ``_set_npc_action_targets`` uses, minus the M2M write (#2637).

    A wind-up has no CombatOpponentAction row to attach an M2M to at
    declaration time — ``PendingOpponentAttack.target`` is a single nullable
    FK instead (v1 single-target). The caller collapses a one-element,
    participant-targeting selection into that FK; anything else (multi/ALL,
    or an opponent-targeting summon windup) stays room-targeting (``None``),
    re-derived at maturation.
    """
    if targeting_participants:
        return _select_targets(
            entry,
            target_pool,
            rotation=rotation,
            _threat_map=threat_map,
            _shield_participant_ids=shield_participant_ids,
        )
    # See _set_npc_action_targets: never forward the participant-keyed maps
    # into opponent-targeting selection (threat-map pk collision, #4091).
    return _select_opponent_targets(
        entry,
        target_pool,
        rotation=rotation,
        _threat_map=None,
        _shield_participant_ids=None,
    )


def _dual_dispatch_combat_narration(encounter: CombatEncounter, narration: str) -> None:
    """Broadcast a combat narration line to BOTH clients (HARD telnet parity).

    Mirrors ``world.covenants.perks.services.announce_fired_perks``'s
    dual-dispatch shape: a persisted, Narrator-authored OUTCOME Interaction
    over the WS interaction payload
    (``world.combat.interaction_services.broadcast_action_outcome``) PLUS a
    direct ``room.msg_contents(narration)`` text companion so bare telnet
    clients render the identical line — ``broadcast_action_outcome`` alone is
    WS-only.
    """
    from world.combat.interaction_services import broadcast_action_outcome  # noqa: PLC0415

    broadcast_action_outcome(encounter=encounter, narration=narration)
    room = encounter.room
    if room is not None:
        room.msg_contents(narration)


def _find_windup_caller(encounter: CombatEncounter) -> CombatParticipant | None:
    """First ACTIVE participant flagged to auto-call enemy wind-ups (#2637 design 6).

    A participant qualifies when their character holds an active
    (``left_at__isnull=True``), engaged ``CharacterCovenantRole`` whose
    ``covenant_role`` (or that role's ``parent_role`` — the riding rule
    mirrors ``CovenantRole.blend_weight_for``) has ``calls_out_windups=True``.
    Deterministic by participant pk. Two queries total (participants, then one
    batched membership query), never a query per candidate.
    """
    from world.covenants.models import CharacterCovenantRole  # noqa: PLC0415

    participants = list(
        CombatParticipant.objects.filter(
            encounter=encounter,
            status=ParticipantStatus.ACTIVE,
        )
        .select_related("character_sheet__character")
        .order_by("pk")
    )
    if not participants:
        return None

    sheet_ids = [p.character_sheet_id for p in participants]
    flagged_sheet_ids = set(
        CharacterCovenantRole.objects.filter(
            character_sheet_id__in=sheet_ids,
            engaged=True,
            left_at__isnull=True,
        )
        .filter(
            Q(covenant_role__calls_out_windups=True)
            | Q(covenant_role__parent_role__calls_out_windups=True)
        )
        .values_list("character_sheet_id", flat=True)
    )
    for participant in participants:
        if participant.character_sheet_id in flagged_sheet_ids:
            return participant
    return None


def _broadcast_commitment_line(encounter: CombatEncounter, narration: str) -> None:
    """Shared dispatch core for either side's multi-round commitment (#2637 NPC, #2705 PC).

    ``PendingOpponentAttack`` (NPC wind-up) and ``SustainedAction`` (PC sustain)
    each narrate from a different subject — an ``opponent.name`` vs a
    participant's character name plus ``sustained.subject_name`` — so a single
    row-polymorphic helper would just branch on type at every call. What both
    rows genuinely share is the *dispatch*: one narration line, broadcast to
    both the WS interaction payload and the telnet room. That is the only
    thing this function generalises; every ``_broadcast_windup_*`` /
    ``_broadcast_sustained_*`` wrapper below builds its own narration text and
    calls this once.
    """
    _dual_dispatch_combat_narration(encounter, narration)


def _broadcast_windup_telegraph(pending: PendingOpponentAttack, *, caller_name: str | None) -> None:
    """Announce a newly-declared wind-up, always naming its target (#2637 design 2, 6; #3572)."""
    target_name = (
        str(pending.target.character_sheet.character)
        if pending.target is not None
        else WINDUP_NO_TARGET_LABEL
    )
    template = pending.threat_entry.windup_telegraph or WINDUP_GENERIC_TELEGRAPH
    if "{target}" not in template:
        template = template + WINDUP_TARGET_CLAUSE
    narration = template.format(opponent=pending.opponent.name, target=target_name)
    if caller_name:
        narration = f"{narration} - {caller_name} calls it!"
    _svc._broadcast_commitment_line(pending.encounter, narration)  # noqa: SLF001 (test patch seam)


def _broadcast_windup_wreck(pending: PendingOpponentAttack, attacker_name: str) -> None:
    """Announce a PC hit staggering a winding-up opponent (#2637 design 4)."""
    narration = f"{attacker_name}'s strike staggers {pending.opponent.name}'s wind-up!"
    _svc._broadcast_commitment_line(pending.encounter, narration)  # noqa: SLF001 (test patch seam)


def _broadcast_windup_fizzled(pending: PendingOpponentAttack, *, reason: str = "") -> None:
    """Announce a wind-up that never lands (#2637 design 3)."""
    if reason:
        narration = f"{pending.opponent.name}'s wind-up {reason} and comes to nothing!"
    else:
        narration = (
            f"{pending.opponent.name}'s wind-up is broken entirely — the perfect chain cancels it!"
        )
    _svc._broadcast_commitment_line(pending.encounter, narration)  # noqa: SLF001 (test patch seam)


def _broadcast_sustained_telegraph(sustained: SustainedAction) -> None:
    """Announce a newly-declared PC sustained action (#2705).

    Always ``SUSTAINED_GENERIC_TELEGRAPH`` — unlike the NPC wind-up side,
    neither ``Technique`` nor ``Ritual`` authors a per-subject telegraph line
    (there is no analogous field), so there is nothing to fall back FROM.
    """
    character_name = str(sustained.participant.character_sheet.character)
    narration = SUSTAINED_GENERIC_TELEGRAPH.format(
        character=character_name, subject=sustained.subject_name
    )
    _svc._broadcast_commitment_line(sustained.encounter, narration)  # noqa: SLF001 (test patch seam)


def _broadcast_sustained_erosion(sustained: SustainedAction) -> None:
    """Announce a landing hit chipping away at a PC's sustained action (#2705).

    The PC-side sibling of ``_broadcast_windup_wreck``. No called-out variant:
    a PC wind-up is public by construction (it is announced the round it is
    declared, via ``_broadcast_sustained_telegraph``), never a designed reveal
    the way an unflagged NPC wind-up is — so there is only ever one erosion
    line, not a blind/called-out pair.
    """
    character_name = str(sustained.participant.character_sheet.character)
    narration = f"{character_name}'s hold on {sustained.subject_name} takes a blow!"
    _svc._broadcast_commitment_line(sustained.encounter, narration)  # noqa: SLF001 (test patch seam)


def _broadcast_sustained_broken(sustained: SustainedAction, *, reason: str = "") -> None:
    """Announce a PC sustained action breaking before it matures (#2705).

    The PC-side sibling of ``_broadcast_windup_fizzled``. Fires when
    ``downgrades >= absorption_budget`` at maturation, or when the
    participant can no longer hold the commitment together (left/died).
    """
    character_name = str(sustained.participant.character_sheet.character)
    if reason:
        narration = f"{character_name}'s hold on {sustained.subject_name} {reason}!"
    else:
        narration = f"{character_name}'s hold on {sustained.subject_name} breaks entirely!"
    _svc._broadcast_commitment_line(sustained.encounter, narration)  # noqa: SLF001 (test patch seam)
