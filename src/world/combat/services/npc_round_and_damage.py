"""NPC action selection for a round and opponent damage application."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import TYPE_CHECKING

from flows.constants import EventName
from flows.events.payloads import CharacterIncapacitatedPayload, DamagePreApplyPayload
from world.combat import services as _svc
from world.combat.constants import (
    ENEMY_LANE_CAP_PERCENT,
    EngagementLockStatus,
    OpponentStatus,
    OpponentTier,
    ParticipantStatus,
)
from world.combat.damage_source import classify_source
from world.combat.models import (
    CombatEncounter,
    CombatOpponent,
    CombatOpponentAction,
    CombatParticipant,
    CombatRoundAction,
    EngagementLock,
    ThreatPoolEntry,
    ThreatRecord,
)
from world.combat.services.declaration_phase import _get_eligible_entries
from world.combat.services.declare_action import (
    _COMPANION_HOLD,
    _apply_companion_order,
    _batch_fetch_cooldown_data,
    _npc_action_target_pool,
)
from world.combat.services.foundations import accumulate_threat
from world.combat.services.windup_and_attacks import (
    _execute_npc_attack,
    swarm_attack_count,
    swarm_kills,
)
from world.combat.types import OpponentDamageResult
from world.conditions.constants import Allegiance
from world.scenes.constants import RoundStatus

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.conditions.models import DamageType
    from world.conditions.types import DamageInteractionResult
    from world.magic.models import Technique


def select_npc_actions(
    encounter: CombatEncounter,
) -> list[CombatOpponentAction]:
    """Select and create NPC actions for the current round.

    For each active opponent with a threat pool, picks a weighted-random
    entry from eligible threat pool entries and assigns targets. Targeting is
    allegiance-aware (#1590, #4091, ADR-0058 as amended by ADR-4091): a charmed
    opponent (``ALLY_OF_CASTER``) targets ENEMY/TURNED opponents, a turned
    opponent (``TURNED``) targets its own former (stored-ENEMY) side, and a
    calmed opponent (``NEUTRAL``) holds and takes no action; an opponent left
    with no valid targets skips the round.

    Raises ValueError if the encounter is not in DECLARING status.
    """
    if encounter.status != RoundStatus.DECLARING:
        msg = (
            f"Cannot select NPC actions: encounter status is "
            f"'{encounter.get_status_display()}', expected 'Declaring'."
        )
        raise ValueError(msg)

    # Auto-lock formation: check threat thresholds before NPC targeting (#2020).
    from world.combat.engagement_locks import check_auto_lock_formation  # noqa: PLC0415

    check_auto_lock_formation(encounter)

    opponents = list(
        CombatOpponent.objects.filter(
            encounter=encounter,
            status=OpponentStatus.ACTIVE,
        )
        .exclude(threat_pool__isnull=True)
        .exclude(mirrors_participant_id__isnull=False)
        .select_related("threat_pool")
    )

    if not opponents:
        return []

    # Effective allegiance for every active opponent, computed once per round
    # (#4091) — includes opponents with no threat pool (e.g. mirrored bosses)
    # so a charmed/turned attacker's hostile pool sees the whole encounter.
    from world.npc_services.allegiance import effective_allegiances  # noqa: PLC0415

    all_active = list(
        CombatOpponent.objects.filter(encounter=encounter, status=OpponentStatus.ACTIVE)
    )
    allegiances = effective_allegiances(all_active)

    # Batch-prefetch all threat pool entries for all opponent pools
    pool_ids = {o.threat_pool_id for o in opponents if o.threat_pool_id}
    all_entries = list(ThreatPoolEntry.objects.filter(pool_id__in=pool_ids))
    entries_by_pool: dict[int, list[ThreatPoolEntry]] = defaultdict(list)
    for entry in all_entries:
        entries_by_pool[entry.pool_id].append(entry)

    recently_used_by_opponent = _batch_fetch_cooldown_data(
        opponents,
        entries_by_pool,
        all_entries,
        encounter.round_number,
    )

    # Design: NPCs target PCs who can still act (not dead, not incapacitated).
    # Unconscious PCs (awareness 0) are "down" and not picked as targets; a
    # dying-but-conscious PC remains in the fight and is targetable. can_act is
    # the same coarse agency gate used for declaration eligibility.
    # Intangible PCs (incorporeal, sunk, phased) are also excluded (#1584 Task 8).
    from world.conditions.services import is_untargetable  # noqa: PLC0415
    from world.vitals.services import can_act  # noqa: PLC0415

    candidate_participants = list(
        CombatParticipant.objects.filter(
            encounter=encounter,
            status=ParticipantStatus.ACTIVE,
        ).select_related("character_sheet__character")
    )
    active_participants = [
        p
        for p in candidate_participants
        if can_act(p.character_sheet) and not is_untargetable(p.character_sheet.character)
    ]

    # Batch-prefetch ThreatRecord data for HIGHEST_THREAT/SPECIFIC_ROLE (#2020)
    active_participant_ids = [p.pk for p in active_participants]
    threat_maps: dict[int, dict[int, int]] = defaultdict(dict)
    if active_participant_ids:
        for tr in ThreatRecord.objects.filter(
            opponent__in=opponents,
            participant_id__in=active_participant_ids,
        ):
            threat_maps[tr.opponent_id][tr.participant_id] = tr.threat_value

    # Batch-prefetch active EngagementLocks for lock narrowing (#2020)
    active_locks_by_opponent: dict[int, int] = {}
    for lock in EngagementLock.objects.filter(
        encounter=encounter,
        opponent__in=opponents,
        status=EngagementLockStatus.ACTIVE,
    ).values("opponent_id", "participant_id"):
        active_locks_by_opponent[lock["opponent_id"]] = lock["participant_id"]

    # Batch-prefetch SHIELD-axis (blend weight > 0) participant IDs for SPECIFIC_ROLE (#2020)
    from world.covenants.constants import RoleArchetype  # noqa: PLC0415
    from world.covenants.services import precedence_role_for_combat  # noqa: PLC0415

    shield_participant_ids: set[int] = set()
    for p in active_participants:
        role = precedence_role_for_combat(p.character_sheet)
        if role is not None and role.blend_weight_for(RoleArchetype.SHIELD) > 0:
            shield_participant_ids.add(p.pk)

    actions: list[CombatOpponentAction] = []

    for opponent in opponents:
        pool_entries = entries_by_pool.get(opponent.threat_pool_id, [])
        cooldown_used = recently_used_by_opponent.get(opponent.pk, set())
        actions.extend(
            _build_opponent_round_actions(
                opponent,
                pool_entries,
                cooldown_used,
                active_participants,
                encounter,
                threat_map=threat_maps.get(opponent.pk),
                shield_participant_ids=shield_participant_ids,
                locked_participant_id=active_locks_by_opponent.get(opponent.pk),
                allegiances=allegiances,
                active_opponents=all_active,
            )
        )

    return actions


def _build_opponent_round_actions(  # noqa: PLR0913
    opponent: CombatOpponent,
    pool_entries: list[ThreatPoolEntry],
    cooldown_used: set[int],
    active_participants: list[CombatParticipant],
    encounter: CombatEncounter,
    *,
    threat_map: dict[int, int] | None = None,
    shield_participant_ids: set[int] | None = None,
    locked_participant_id: int | None = None,
    allegiances: dict[int, Allegiance],
    active_opponents: list[CombatOpponent],
) -> list[CombatOpponentAction]:
    """Create one opponent's NPC action rows for the current round.

    Returns the created actions, or an empty list when the opponent skips the
    round — no eligible (off-cooldown) threat entry, or the empty-pool guard:
    no valid target (a #1584 ALLY summon or #4091 charmed/turned NPC with no
    live hostile, or a #1590 calmed/neutral opponent).
    """
    from world.combat.morale import (  # noqa: PLC0415
        OpponentMoraleState,
        morale_state_for,
    )

    # Break: a broken opponent flees — set FLED and skip the round (#2015).
    if morale_state_for(opponent) == OpponentMoraleState.BREAK:
        opponent.status = OpponentStatus.FLED
        opponent.save(update_fields=["status"])
        return []

    eligible = _get_eligible_entries(opponent, pool_entries, cooldown_used)
    if not eligible:
        return []

    target_pool, targeting_participants = _npc_action_target_pool(
        opponent,
        active_participants,
        encounter,
        allegiances=allegiances,
        active_opponents=active_opponents,
    )
    if not target_pool:
        return []

    # Lock narrowing: if an active EngagementLock exists, narrow to the locked PC (#2020).
    if locked_participant_id is not None and targeting_participants:
        locked_pool = [p for p in target_pool if p.pk == locked_participant_id]
        if locked_pool:
            target_pool = locked_pool

    # --- Companion order integration (#1921) ---
    # An ALLY summon with a CompanionOrder may override its target or skip.
    companion_result = _apply_companion_order(opponent, encounter.round_number, target_pool)
    if companion_result is _COMPANION_HOLD:
        return []
    if isinstance(companion_result, list):
        target_pool = companion_result

    if opponent.tier == OpponentTier.SWARM and opponent.swarm_count is not None:
        n_attacks = swarm_attack_count(
            opponent.swarm_count,
            opponent.bodies_per_attack or 1,
            len(target_pool),
        )
    else:
        n_attacks = opponent.actions_per_round

    actions: list[CombatOpponentAction] = []
    for attack_index in range(n_attacks):
        _execute_npc_attack(
            opponent=opponent,
            eligible=eligible,
            encounter=encounter,
            target_pool=target_pool,
            targeting_participants=targeting_participants,
            rotation=attack_index,
            threat_map=threat_map,
            shield_participant_ids=shield_participant_ids,
            actions=actions,
        )

    return actions


def _zero_opponent_damage_result(opponent: CombatOpponent) -> OpponentDamageResult:
    """A no-effect damage result (hit cancelled or reduced to nothing)."""
    return OpponentDamageResult(
        damage_dealt=0,
        health_damaged=False,
        probed=False,
        probing_increment=0,
        defeated=False,
        kills=0,
        opponent_id=opponent.pk,
    )


def _apply_swarm_damage(opponent: CombatOpponent, raw_damage: int) -> OpponentDamageResult:
    """Resolve a landing hit on a SWARM opponent (#875).

    Swarms have no HP, soak, or probing — a landing attack clears bodies.
    """
    kills = min(swarm_kills(raw_damage, opponent.body_toughness or 1), opponent.swarm_count)
    opponent.swarm_count -= kills
    defeated = opponent.swarm_count <= 0
    if defeated:
        opponent.status = OpponentStatus.DEFEATED
    opponent.save(update_fields=["swarm_count", "status"])
    return OpponentDamageResult(
        damage_dealt=kills,
        health_damaged=False,
        probed=False,
        probing_increment=0,
        defeated=defeated,
        kills=kills,
        opponent_id=opponent.pk,
    )


def _emit_opponent_pre_apply(
    opponent: CombatOpponent,
    raw_damage: int,
    damage_type: DamageType | None,
    source_sheet: CharacterSheet | None,
) -> tuple[int, bool]:
    """Emit DAMAGE_PRE_APPLY for an opponent; return ``(amount, dropped)``.

    Mirrors the participant path so reactive defences (force-field/reflect/blink)
    fire on NPCs and ALLY summons identically (#1584). Returns the possibly
    mutated damage amount and whether the hit should be dropped — the event
    cancelled it, or the mutated amount fell to <= 0. Opponents with no
    objectdb/location skip the event (amount unchanged, never dropped here).
    """
    if opponent.objectdb is None or opponent.objectdb.location is None:
        return raw_damage, False
    damage_source = classify_source(source_sheet.character if source_sheet is not None else None)
    pre_payload = DamagePreApplyPayload(
        target=opponent.objectdb,
        amount=raw_damage,
        damage_type=damage_type,
        source=damage_source,
    )
    stack = _svc.emit_event(
        EventName.DAMAGE_PRE_APPLY,
        pre_payload,
        location=opponent.objectdb.location,
    )
    if stack.was_cancelled():
        return raw_damage, True
    return pre_payload.amount, pre_payload.amount <= 0


def _resolve_opponent_defeat(opponent: CombatOpponent, source_sheet: CharacterSheet | None) -> bool:
    """Resolve whether an opponent at 0 HP is actually defeated.

    Story-criticality check: prevent death if the NPC is load-bearing for a
    story the attacker isn't part of (#1874). When death is prevented, the
    NPC flees instead and ``False`` is returned. Otherwise the opponent's
    status is set to DEFEATED and ``True`` is returned.
    """
    from world.stories.flee_services import flee_story_critical_npc  # noqa: PLC0415
    from world.stories.npc_protection import (  # noqa: PLC0415
        is_death_prevented_by_story,
    )

    npc_sheet = None
    if opponent.objectdb is not None:
        try:
            npc_sheet = opponent.objectdb.sheet_data
        except AttributeError:
            npc_sheet = None
    attacker = source_sheet.character if source_sheet else None
    if npc_sheet is not None and is_death_prevented_by_story(npc_sheet, attacker):
        flee_story_critical_npc(opponent, attacker)
        return False
    opponent.status = OpponentStatus.DEFEATED
    return True


def _emit_companion_fall(opponent: CombatOpponent) -> None:
    """Announce a bonded companion's defeat to the surge engine (#3575).

    Only a companion-backed ALLY opponent (``summoned_by`` set, a live unreleased
    ``Companion`` owning ``objectdb``) emits; a plain summon, a persona-backed NPC
    and every ENEMY stay silent as before. Emits CHARACTER_INCAPACITATED, never
    CHARACTER_KILLED: defeat is not death (#1873 resolves death at encounter end),
    and the KILLED subscribers (asset loss, death deferral) are for people. Both
    events reach ``relationship_spike_handler`` and dedup to one ALLY_FALLEN.
    The "is this ally someone's companion" predicate now lives in
    ``world.companions.services.resolve_bonded_companion`` (#3652), shared with
    the encounter/battle defeat hooks so it is not spelled a third time.
    """
    from world.companions.services import resolve_bonded_companion  # noqa: PLC0415

    if resolve_bonded_companion(opponent) is None:
        return
    room = opponent.encounter.room
    if room is None:
        return
    _svc.emit_event(
        EventName.CHARACTER_INCAPACITATED,
        CharacterIncapacitatedPayload(
            character=opponent.objectdb,
            source_event=EventName.DAMAGE_PRE_APPLY,
        ),
        location=room,
    )


def _is_vulnerable(opponent: CombatOpponent) -> bool:
    """Return True if the opponent's break-bar vulnerability window is active."""
    return opponent.vulnerability_rounds_remaining > 0


def _effective_soak_for_opponent(opponent: CombatOpponent, bypass_soak: bool) -> int:
    """Return the effective soak value, bypassed by bypass_soak or vulnerability."""
    if bypass_soak or _is_vulnerable(opponent):
        return 0
    return opponent.soak_value


def _effective_resistance_for_opponent(
    opponent: CombatOpponent, damage_type: DamageType | None
) -> int:
    """Return damage-type resistance, bypassed during vulnerability window."""
    if damage_type is None or opponent.objectdb is None or _is_vulnerable(opponent):
        return 0
    return opponent.objectdb.conditions.resistance_modifier(damage_type)


def _apply_condition_damage_interactions(
    target: ObjectDB,  # noqa: OBJECTDB_PARAM
    damage_type: DamageType | None,
    damage_amount: int,
) -> tuple[int, DamageInteractionResult | None]:
    """Run condition-damage interactions on a target, returning modified damage + result.

    Called from both combat damage paths after soak/resistance/armor (#2018).
    The interaction modifier is a final percentage multiplier on net damage — SUMMED
    across every matching ``ConditionDamageInteraction`` row, then clamped to
    ``±ENEMY_LANE_CAP_PERCENT`` (#2643, Undermine's enemy-side lane; the same EQ2 lane
    guard as the team-damage-percent lane — see ``world.magic.constants
    .TEAM_BUFF_LANE_CAP_PERCENT``). The clamp applies to the summed percent, not to any
    individual authored row — an authored row may itself exceed the band; only the
    live total a target can accumulate is bounded.
    Returns ``(modified_damage, interaction_result)`` — ``interaction_result``
    is None when damage_type is None, a non-model value, or damage_amount is zero.
    """
    if damage_type is None or damage_amount <= 0:
        return damage_amount, None
    # Some callers pass a string damage_type (e.g. "physical") rather than a
    # DamageType model instance. Condition-damage interactions require a real
    # model to query the interaction table — skip for non-model values.
    from world.conditions.models import DamageType  # noqa: PLC0415

    if not isinstance(damage_type, DamageType):
        return damage_amount, None
    from world.conditions.services import process_damage_interactions  # noqa: PLC0415

    result = process_damage_interactions(target, damage_type)
    if result.damage_modifier_percent != 0:
        clamped_percent = max(
            -ENEMY_LANE_CAP_PERCENT, min(ENEMY_LANE_CAP_PERCENT, result.damage_modifier_percent)
        )
        damage_amount = max(0, int(damage_amount * (1 + clamped_percent / 100)))
    return damage_amount, result


def _opponent_health_before_pct(opponent: CombatOpponent) -> float:
    """Pre-hit health fraction for an opponent (#2643 execute basis). 0.0 when maxless."""
    if opponent.max_health <= 0:
        return 0.0
    return max(0.0, opponent.health / opponent.max_health)


def _apply_execute_multiplier(
    damage_amount: int, multiplier: Decimal, health_before_pct: float
) -> int:
    """Scale damage up as the target's PRE-hit health runs low (#2643 execute).

    ``factor = 1 + multiplier * missing_health_fraction`` where
    ``missing_health_fraction = 1 - health_before_pct``. A zero (the default on every
    damage profile) or falsy ``multiplier`` is a byte-identical no-op — every existing
    damage test is unaffected. Basis is always PRE-hit health (captured by the caller
    before this hit's own subtraction), so a second hit in the same exchange correctly
    prices off the health the FIRST hit left behind — never a recursive
    self-referential fraction, no matter how many hits land in sequence.
    """
    if not multiplier:
        return damage_amount
    missing_health_fraction = 1.0 - health_before_pct
    factor = 1 + float(multiplier) * missing_health_fraction
    return max(0, int(damage_amount * factor))


def _break_engagement_lock_on_defeat(
    opponent: CombatOpponent, *, reason: str | None = None
) -> None:
    """Release the opponent's active engagement lock, if any, on its defeat (#2020).

    ``reason`` defaults to ``LockBreakReason.DEFEAT`` (the original call site);
    ``remove_opponent`` (#3382) passes ``LockBreakReason.REMOVED`` for a GM pull,
    reusing this same lock-breaking seam rather than duplicating the query.
    """
    from world.combat.constants import LockBreakReason  # noqa: PLC0415
    from world.combat.engagement_locks import break_engagement_lock  # noqa: PLC0415

    active_lock = EngagementLock.objects.filter(
        opponent=opponent,
        status=EngagementLockStatus.ACTIVE,
    ).first()
    if active_lock is not None:
        break_engagement_lock(active_lock, reason=reason or LockBreakReason.DEFEAT)


def _accumulate_damage_threat(
    opponent: CombatOpponent, source_sheet: CharacterSheet, damage_through: int
) -> None:
    """Credit post-soak damage to the dealer's ThreatRecord for this opponent (#2020)."""
    participant = CombatParticipant.objects.filter(
        encounter=opponent.encounter,
        character_sheet=source_sheet,
    ).first()
    if participant is not None:
        accumulate_threat(opponent.encounter, opponent, participant, damage_through)


def _maybe_trigger_lock_interference(
    opponent: CombatOpponent, source_sheet: CharacterSheet
) -> None:
    """Fire the duel-interference beat when a non-locked PC hits a locked opponent (#3447).

    The narrative payoff #2020 designed but never called: the locked duelist's
    ``break_in_consequence_pool`` fires and an INTERFERENCE dramatic surge lands
    on them (see :func:`world.combat.engagement_locks.trigger_interference_drama`).
    Dedup rides the surge's own ``DramaticSurgeRecord`` trail — checked here (not
    only inside ``apply_dramatic_surge``) so once the surge has fired, the
    consequence-pool leg cannot repeat on later hits: at most one full beat per
    (locked duelist, interloper) per encounter. A record only exists when the
    encounter's escalation curve actually surged, so a lock authored with a
    ``break_in_consequence_pool`` on a curve-less encounter refires the pool per
    landing hit — author such pools one-shot-safe, or give the encounter a curve.
    """
    from world.combat.constants import SurgeTriggerKind  # noqa: PLC0415
    from world.combat.engagement_locks import trigger_interference_drama  # noqa: PLC0415
    from world.combat.models import DramaticSurgeRecord  # noqa: PLC0415

    active_lock = (
        EngagementLock.objects.filter(
            opponent=opponent,
            status=EngagementLockStatus.ACTIVE,
        )
        .select_related("participant")
        .first()
    )
    if active_lock is None or active_lock.participant.character_sheet_id == source_sheet.pk:
        return

    interloper = CombatParticipant.objects.filter(
        encounter=opponent.encounter,
        character_sheet=source_sheet,
    ).first()
    if interloper is None:
        return

    already_fired = DramaticSurgeRecord.objects.filter(
        encounter=opponent.encounter,
        participant=active_lock.participant,
        trigger_kind=SurgeTriggerKind.INTERFERENCE,
        subject_sheet=source_sheet,
    ).exists()
    if already_fired:
        return

    trigger_interference_drama(active_lock, interloper)


def increment_probing(opponent: CombatOpponent, amount: int) -> None:
    """Add ``amount`` to an opponent's probing counter (clamped at zero) and persist.

    Single standalone write path for ``probing_current`` used by combo-opening
    passives so probing feeds combo detection identically to damage-sourced probing.
    """
    opponent.probing_current = max(0, opponent.probing_current + amount)
    opponent.save(update_fields=["probing_current"])


def _apply_passive_technique(
    technique: Technique,
    participant: CombatParticipant,
    encounter: CombatEncounter,
) -> None:
    """Apply a declared passive technique's authored conditions with NO dice roll.

    A passive IS a Technique with authored ``TechniqueAppliedCondition`` rows.
    Each row is applied at fixed scaling — ``effective_power=technique.intensity``
    and ``success_level=row.minimum_success_level`` — so no ``CheckResult`` is
    constructed and no offense roll happens (contrast ``CombatTechniqueResolver``,
    which is roll/damage-bound). Reuses ``bulk_apply_conditions`` so passives feed
    the exact same condition machinery as the focused path.

    Target resolution (v1):

    - ``SELF`` → the actor's own character.
    - ``ENEMY`` → every ACTIVE opponent's ``objectdb`` whose EFFECTIVE allegiance
      is not ALLY_OF_CASTER (#1584, #4091). An ALLY summon or a charmed NPC fights
      on the actor's side, so enemy-targeted AoE never lands on either; a TURNED
      or calmed (NEUTRAL) opponent is still the party's opponent for a passive —
      only a charmed/summoned ally is spared. Mirrors ``_resolve_condition_target``'s
      ENEMY branch, which returns ``opp.objectdb`` for an active opponent. Every
      opponent (including ephemeral CombatNPCs) is created with an ObjectDB by
      ``add_opponent``; the FK is only nulled if the ObjectDB is destroyed
      externally, so we skip opponents whose ``objectdb`` is None — matching the
      focused path's None-guard.
    - ``ALLY`` → every ACTIVE participant except the actor.

    When ``technique.combo_opening_probing`` is set, every such ACTIVE opponent
    gains that much probing (the combo-opening reward) via ``increment_probing`` —
    the combo-opening effect for ephemeral opponents regardless of conditions.
    """
    from world.conditions.services import bulk_apply_conditions  # noqa: PLC0415
    from world.conditions.types import BulkConditionApplication  # noqa: PLC0415
    from world.magic.models.techniques import ConditionTargetKind  # noqa: PLC0415
    from world.npc_services.allegiance import effective_allegiances  # noqa: PLC0415

    actor = participant.character_sheet.character

    # Batch the opponent/ally queries ONCE before the row loop (no queries in loop).
    active_opponents = list(
        CombatOpponent.objects.filter(
            encounter=encounter,
            status=OpponentStatus.ACTIVE,
        ).select_related("objectdb")
    )
    allegiances = effective_allegiances(active_opponents)
    active_allies = list(
        CombatParticipant.objects.filter(
            encounter=encounter,
            status=ParticipantStatus.ACTIVE,
        )
        .exclude(pk=participant.pk)
        .select_related("character_sheet__character")
    )

    # Combo-opening probing: granted to every opponent not fighting on the actor's
    # side, independent of any condition application (the combo-opening effect for
    # ephemeral opponents). A charmed/summoned ally is on the actor's side, so
    # probing it is meaningless (#1584); a turned or calmed opponent still gets it.
    if technique.combo_opening_probing:
        for opp in active_opponents:
            if allegiances[opp.pk] != Allegiance.ALLY_OF_CASTER:
                increment_probing(opp, technique.combo_opening_probing)

    # resolve_round prefetches ``..._passive__condition_applications__condition`` so
    # this ``.all()`` reads the prefetch cache (no per-passive query in the resolution
    # loop). Standalone callers fall back to lazy loads. Do NOT add ``.select_related``
    # here — it forces a fresh query and bypasses the prefetch cache.
    rows = list(technique.condition_applications.all())
    if not rows:
        return

    applications: list[BulkConditionApplication] = []
    for row in rows:
        severity = row.compute_severity(
            effective_power=technique.intensity,
            success_level=row.minimum_success_level,
        )
        duration = row.compute_duration_rounds(
            effective_power=technique.intensity,
            success_level=row.minimum_success_level,
        )

        if row.target_kind == ConditionTargetKind.SELF:
            targets = [actor]
        elif row.target_kind == ConditionTargetKind.ENEMY:
            targets = [
                opp.objectdb
                for opp in active_opponents
                if allegiances[opp.pk] != Allegiance.ALLY_OF_CASTER and opp.objectdb is not None
            ]
        elif row.target_kind == ConditionTargetKind.ALLY:
            targets = [ally.character_sheet.character for ally in active_allies]
        else:
            targets = []

        applications.extend(
            BulkConditionApplication(
                target=target,
                template=row.condition,
                severity=severity,
                duration_rounds=duration,
                stack_count=row.stack_count,
            )
            for target in targets
        )

    if not applications:
        return

    bulk_apply_conditions(
        applications,
        source_character=actor,
        source_technique=technique,
        source_description=f"passive: {technique.name}",
    )


def _refresh_participant_trigger_handlers(encounter: CombatEncounter) -> None:
    """Make passive-installed reactive triggers visible within the same round.

    ``_resolve_passive_actions`` may install reactive conditions (e.g. DEFEND's
    Shielded) on allies. Installing a reactive condition creates ``Trigger`` rows
    and calls ``TriggerHandler.on_trigger_added`` → ``invalidate``, which defers the
    cache reset to ``transaction.on_commit``. But ``resolve_round`` runs the whole
    round inside one ``@transaction.atomic`` block, so that ``on_commit`` callback
    does not fire until *after* this round's damage resolution — meaning the new
    triggers would be invisible to the very NPC attack they are meant to mitigate.

    Synchronously refresh each active participant's character trigger handler so the
    freshly ``bulk_create``d rows (already visible in this transaction) are loaded
    before ``_resolve_actions`` runs. The deferred ``on_commit(_reset)`` remains
    intact as the cross-transaction/rollback safety net.
    """
    participants = CombatParticipant.objects.filter(
        encounter=encounter,
        status=ParticipantStatus.ACTIVE,
    ).select_related("character_sheet__character")
    for participant in participants:
        character = participant.character_sheet.character
        handler = character.trigger_handler
        if handler is not None:
            handler.refresh()


def _resolve_passive_actions(
    encounter: CombatEncounter,
    pc_actions: dict[int, CombatRoundAction],
) -> None:
    """Apply every declared passive on every PC action before focused resolution.

    Runs before ``_resolve_actions`` so defensive/buff passives land before any
    focused or NPC action resolves this round.
    """
    for action in pc_actions.values():
        for passive in (
            action.physical_passive,
            action.social_passive,
            action.mental_passive,
        ):
            if passive is not None:
                _apply_passive_technique(passive, action.participant, encounter)
