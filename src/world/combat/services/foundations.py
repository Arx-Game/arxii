"""Shared combat helpers: threat records, participants, and target resolution."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from flows.constants import EventName
from flows.events.payloads import CharacterKilledPayload
from world.checks.services import perform_check_with_modifiers
from world.combat import services as _svc
from world.combat.constants import (
    CONCENTRATION_CHECK_TYPE_NAME,
    PENETRATION_CHECK_TYPE_NAME,
    SUSTAINED_BASE_ABSORPTION,
    SUSTAINED_MAX_ABSORPTION,
    SUSTAINED_MIN_ABSORPTION,
    CombatAllegiance,
    OpponentStatus,
    OpponentTier,
    ParticipantStatus,
)
from world.combat.models import (
    CombatEncounter,
    CombatOpponent,
    CombatParticipant,
    CombatRoundAction,
    EncounterRiskAcknowledgement,
    FleeConfig,
    ThreatRecord,
)
from world.conditions.constants import Allegiance
from world.magic.constants import EffectKind
from world.scenes.constants import RoundStatus

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from typeclasses.characters import Character
    from world.character_sheets.models import CharacterSheet
    from world.checks.models import CheckType
    from world.covenants.models import CovenantRole
    from world.magic.models import Technique
    from world.traits.models import CheckOutcome

logger = logging.getLogger(__name__)


logger = logging.getLogger(__name__)

# Tri-state sentinel for optional "leave unchanged" kwargs (#3552); mirrors
# world/skills/services.py's _UNSET.
_UNSET = object()

# ---------------------------------------------------------------------------
# Threat record helpers (#2020)
# ---------------------------------------------------------------------------


def get_or_create_threat_record(
    encounter: CombatEncounter,
    opponent: CombatOpponent,
    participant: CombatParticipant,
) -> ThreatRecord:
    """Get or create the ThreatRecord for an (opponent, participant) pairing (#2020).

    Args:
        encounter: The combat encounter.
        opponent: The NPC opponent.
        participant: The PC participant.

    Returns:
        The existing or newly-created ``ThreatRecord`` for this pairing.
    """
    record, _ = ThreatRecord.objects.get_or_create(
        encounter=encounter,
        opponent=opponent,
        participant=participant,
        defaults={"threat_value": 0},
    )
    return record


def accumulate_threat(
    encounter: CombatEncounter,
    opponent: CombatOpponent,
    participant: CombatParticipant,
    amount: int,
) -> None:
    """Increment the threat value for an (opponent, participant) pairing (#2020).

    Called from ``apply_damage_to_opponent`` (damage -> threat) and the taunt
    verb (#2015). ``amount`` is a positive integer; negative values are clamped
    to zero.

    Args:
        encounter: The combat encounter.
        opponent: The NPC opponent being threatened against.
        participant: The PC participant whose threat is accumulating.
        amount: The threat increment (clamped to >= 0).
    """
    record = get_or_create_threat_record(encounter, opponent, participant)
    record.threat_value = max(0, record.threat_value + amount)
    record.save(update_fields=["threat_value"])


def finalize_new_encounter(encounter: CombatEncounter) -> None:
    """Apply the post-creation defaults every "scene-anchored, no explicit room" creation
    caller needs (#3388).

    Extracted from the web ViewSet's ``perform_create`` (#3067) so telnet's
    ``CreateEncounterAction`` gets identical defaulting behavior instead of a second,
    drifting copy. Defaults ``room`` from ``encounter.scene.location`` when the caller
    didn't supply one — every OTHER encounter-creation call site (world.combat.duels,
    world.combat.cast_seed) always threads an explicit room; this is the one shape where
    the caller doesn't have one yet — then assigns the default EscalationCurve via
    ``assign_default_escalation_curve``. An explicit room already set on ``encounter``
    before this call always wins (unchanged from the pre-extraction behavior).
    """
    from world.combat.escalation import assign_default_escalation_curve  # noqa: PLC0415

    if encounter.room_id is None and encounter.scene.location_id is not None:
        encounter.room = encounter.scene.location
        encounter.save(update_fields=["room"])
    assign_default_escalation_curve(encounter)


# ---------------------------------------------------------------------------
# Identity guard helpers
# ---------------------------------------------------------------------------


def is_combat_npc_typeclass(objectdb: ObjectDB) -> bool:
    """Return True iff the ObjectDB's typeclass is the CombatNPC class."""
    from world.combat.typeclasses.combat_npc import CombatNPC  # noqa: PLC0415

    return isinstance(objectdb, CombatNPC)


def has_persistent_identity_references(objectdb: ObjectDB) -> bool:
    """Return True if this ObjectDB is referenced by any model that signals
    persistent identity (Persona, RosterEntry, CharacterSheet, etc.).

    Single source of truth for "is this an ObjectDB any persistent system
    cares about?" — when a new persistent-identity model is added, this
    function adds the corresponding check.
    """
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415
    from world.roster.models import RosterEntry  # noqa: PLC0415
    from world.scenes.models import Persona  # noqa: PLC0415

    if CharacterSheet.objects.filter(character=objectdb).exists():
        return True
    if Persona.objects.filter(character_sheet_id=objectdb.pk).exists():
        return True
    if RosterEntry.objects.filter(character_sheet_id=objectdb.pk).exists():
        return True
    return False


def delete_ephemeral_npc(opponent: CombatOpponent) -> bool:
    """Guarded delete of one ephemeral combat NPC's ``ObjectDB``.

    Layer 5 of the multi-layer guard: a defensive re-check right before the
    delete, in case a corrupt row escaped Layers 1-4.

    ``ObjectDB`` isn't an ``ArxSharedMemoryModel``, so its ``delete()`` nulls
    referrers' FKs via a bulk ``SET_NULL`` UPDATE outside
    ``core.deletion.IdentityMapCollector`` — the cached ``opponent`` would
    otherwise keep reporting the deleted ``objectdb`` forever. Setting the
    field and saving on THIS held instance is enough: idmapper's identity map
    means there is only one cached ``CombatOpponent`` per pk in the process,
    so no further cache flush is needed afterward (fix round 3 — a bare
    ``flush_instance_cache()`` call here previously evicted the ENTIRE class
    cache, including every other live encounter's cached opponents, once per
    mob in the cleanup loop). Mirrors ``release_companion``'s identical
    objectdb-nulling fix (``world/companions/services.py`` — that one keeps
    its own narrower flush; unrelated to this fix).

    Shared by this module's own ``cleanup_completed_encounter`` ephemeral
    sweep and ``world.combat.won_over.delete_won_over_npc`` (#4091 fix round
    2) — one guard, one identity-map fix, not two copies of either.
    """
    objectdb = opponent.objectdb
    if objectdb is None or not opponent.objectdb_is_ephemeral:
        return False
    if not is_combat_npc_typeclass(objectdb):
        logger.error("Refusing to delete: %s is not a CombatNPC typeclass", objectdb)
        return False
    if has_persistent_identity_references(objectdb):
        logger.error("Refusing to delete: %s has persistent identity references", objectdb)
        return False
    objectdb.delete()
    opponent.objectdb = None
    opponent.save(update_fields=["objectdb"])
    return True


def _character_has_death_deferred(character: ObjectDB) -> bool:  # noqa: OBJECTDB_PARAM
    """Return True if the character has any active condition granting death_deferred.

    Delegates to the canonical shared helper in world.conditions.services so
    there is one query definition. Kept as a thin wrapper for call-site
    compatibility within this module.
    """
    from world.conditions.services import has_death_deferred  # noqa: PLC0415

    return has_death_deferred(character)


def _emit_death_gate(character: Character, room: ObjectDB) -> None:  # noqa: OBJECTDB_PARAM
    """Fire the death gate: defer when death-deferred is active, else CHARACTER_KILLED."""
    if _character_has_death_deferred(character):
        from world.vitals.models import CharacterVitals  # noqa: PLC0415

        try:
            vitals = CharacterVitals.objects.get(character_sheet=character.sheet_data)
            vitals.death_deferred_pending = True
            vitals.save(update_fields=["death_deferred_pending"])
        except CharacterVitals.DoesNotExist:
            pass
    else:
        _svc.emit_event(
            EventName.CHARACTER_KILLED,
            CharacterKilledPayload(
                character=character,
                source_event=EventName.DAMAGE_PRE_APPLY,
            ),
            location=room,
        )


def get_penetration_check_type() -> CheckType:
    """Return the seeded 'penetration' CheckType for the ward contest (#639).

    Uses get() — never get_or_create — because this is authored content; a
    chartless fabricated row would silently break the resolution pipeline.
    If the seed is missing, CheckType.DoesNotExist propagates loudly (a real
    misconfiguration), not masked. Mirrors
    ``_get_endure_hallowed_ground_check_type``.
    """
    from world.checks.models import CheckType  # noqa: PLC0415

    return CheckType.objects.get(name=PENETRATION_CHECK_TYPE_NAME)


def get_concentration_check_type() -> CheckType:
    """Return the seeded 'Concentration' CheckType rolled at sustained-action
    declaration (#2705).

    Uses get() — never get_or_create — because this is authored content; a
    chartless fabricated row would silently break the resolution pipeline.
    If the seed is missing, CheckType.DoesNotExist propagates loudly (a real
    misconfiguration), not masked. Mirrors ``get_penetration_check_type``.
    """
    from world.checks.models import CheckType  # noqa: PLC0415

    return CheckType.objects.get(name=CONCENTRATION_CHECK_TYPE_NAME)


def roll_sustained_absorption_budget(
    participant: CombatParticipant,
) -> tuple[int, CheckOutcome | None]:
    """Roll Concentration once to set a sustained action's absorption budget (#2705).

    Uses ``perform_check_with_modifiers`` — NOT plain ``perform_check`` — because
    only the ``_with_modifiers`` wrapper calls ``collect_check_modifiers``, which
    folds in ``ConditionCheckModifier`` rows via ``condition_contributions``. 26
    authored Concentration modifier rows exist across the lore fixtures (blinded,
    stressed, focused, etc.) and they are the entire payoff of rolling this check
    at all — a plain ``perform_check`` call would silently make every one of them
    inert for sustained actions.

    ``budget = clamp(SUSTAINED_BASE_ABSORPTION + result.success_level, MIN, MAX)``.
    The clamp exists because ``CheckOutcome.success_level`` is an authored
    -10..+10 field with no lore fixture pinning its ladder (no ``CheckOutcome``
    row is authored in the lore repo at all — they're built ad hoc by seeds/
    factories with varying ranges). Without the clamp a wide authored ladder
    would produce an absurd absorption budget; clamping to
    ``[SUSTAINED_MIN_ABSORPTION, SUSTAINED_MAX_ABSORPTION]`` preserves the
    spec's intended ladder (Crit Fail 0 ... Crit Success 4) under any chart.

    Returns the clamped budget and the CheckOutcome the roll produced (or None
    if the check produced no outcome), so the caller can snapshot the outcome
    on the SustainedAction row.
    """
    result = perform_check_with_modifiers(
        participant.character_sheet.character,
        get_concentration_check_type(),
        target_difficulty=0,
    )
    budget = max(
        SUSTAINED_MIN_ABSORPTION,
        min(SUSTAINED_MAX_ABSORPTION, SUSTAINED_BASE_ABSORPTION + result.success_level),
    )
    return budget, result.outcome


def get_flee_config() -> FleeConfig:
    """Return the seeded FleeConfig singleton (#878).

    Uses cached_singleton() — never get_or_create — because this is authored
    content; a fabricated row would have no check_type and silently break flee
    resolution. DoesNotExist propagates loudly. Mirrors
    get_penetration_check_type.
    """
    config = FleeConfig.objects.cached_singleton()
    if config is None:
        raise FleeConfig.DoesNotExist
    return config


def _sum_active_flat_bonuses(
    participant: CombatParticipant,
    encounter: CombatEncounter,
) -> int:
    """Sum scaled_value across FLAT_BONUS resolved-effect rows on the
    participant's active CombatPull rows for this encounter.

    Reads through CharacterCombatPullHandler so the cached/prefetched
    list is honored — avoids re-querying.
    """
    character = participant.character_sheet.character
    total = 0
    for pull in character.combat_pulls.active_for_encounter(encounter):
        for eff in pull.resolved_effects_cached:
            if eff.kind == EffectKind.FLAT_BONUS and eff.scaled_value:
                total += eff.scaled_value
    return total


def compute_intensity_for_clash(
    participant: CombatParticipant,
    action: CombatRoundAction,
) -> int:
    """Return technique.intensity + active INTENSITY_BUMP pull bonuses for the clash floor gate.

    Used exclusively to gate the clash-open check (intensity_floor). Future
    intensity-ramp contributions (conditions, items, environment) can be added
    here and they will tighten the floor automatically.
    """
    technique = action.focused_action
    if technique is None:
        return 0
    base = technique.intensity
    encounter = participant.encounter
    pull_bonus = 0
    character = participant.character_sheet.character
    for pull in character.combat_pulls.active_for_encounter(encounter):
        for eff in pull.resolved_effects_cached:
            if eff.kind == EffectKind.INTENSITY_BUMP and eff.scaled_value:
                pull_bonus += eff.scaled_value
    return base + pull_bonus


def _resolve_condition_target(
    kind: str,
    action: CombatRoundAction,
    caster_od: ObjectDB,
) -> ObjectDB | None:
    """Resolve a ConditionTargetKind value to a concrete ObjectDB.

    Returns None when the named target is absent or ineligible (e.g. opponent
    already DEFEATED).
    """
    from world.magic.models.techniques import ConditionTargetKind  # noqa: PLC0415

    if kind == ConditionTargetKind.SELF:
        return caster_od
    if kind == ConditionTargetKind.ALLY:
        ally = action.focused_ally_target
        return ally.character_sheet.character if ally is not None else None
    if kind == ConditionTargetKind.ENEMY:
        opp = action.focused_opponent_target
        if opp is not None:
            opp.refresh_from_db()
        active = opp is not None and opp.status != OpponentStatus.DEFEATED
        return opp.objectdb if active else None
    return None


def _resolve_enemy_condition_targets(
    all_opponents: list[CombatOpponent],
    action: CombatRoundAction,
    caster_od: ObjectDB,
) -> list[ObjectDB]:
    """Resolve the ENEMY condition target list for ``_apply_conditions``.

    AREA / FILTERED_GROUP techniques expand ENEMY to ALL active (non-DEFEATED)
    opponents in ``_resolved_opponent_targets()``; when there are no join-table
    opponents, fall back to the single focused target.
    """
    from world.magic.models.techniques import ConditionTargetKind  # noqa: PLC0415

    if all_opponents:
        enemy_objectdbs: list[ObjectDB] = []
        for opp in all_opponents:
            opp.refresh_from_db()
            if opp.status != OpponentStatus.DEFEATED and opp.objectdb is not None:
                enemy_objectdbs.append(opp.objectdb)
        return enemy_objectdbs
    # No join-table opponents — fall back to the single focused target
    target = _resolve_condition_target(ConditionTargetKind.ENEMY, action, caster_od)
    return [target] if target is not None else []


def _build_affected_targets(
    participant: CombatParticipant,  # noqa: ARG001 - reserved for future signature additions
    action: CombatRoundAction,
) -> list[ObjectDB]:
    """Return the dedup'd ObjectDB list for use_technique's targets parameter.

    Resolution rules:
    - opponent target → opp.objectdb (always present after CombatOpponent refactor;
      None-guarded for pathological state)
    - ally target → ally.character_sheet.character
    - both null → empty list
    """
    targets: list = []
    seen: set[int] = set()
    if action.focused_opponent_target_id:
        opp = action.focused_opponent_target
        od = opp.objectdb
        if od is not None and od.pk not in seen:
            targets.append(od)
            seen.add(od.pk)
    if action.focused_ally_target_id:
        ally_od = action.focused_ally_target.character_sheet.character
        if ally_od.pk not in seen:
            targets.append(ally_od)
            seen.add(ally_od.pk)
    return targets


def _resolve_primary_target_sheet(action: CombatRoundAction) -> CharacterSheet | None:
    """Resolve the cast's primary target's ``CharacterSheet`` for situational perks (#2536).

    Mirrors ``_build_affected_targets``'s ordering (opponent target takes
    precedence over ally target when a technique somehow declares both — the
    dispatcher never actually does this, but the ordering is kept consistent).
    Only a PC/sheet-backed target can populate a ``CharacterSheet``:

    - ``focused_ally_target`` → ``CombatParticipant.character_sheet`` (always
      a real ``CharacterSheet`` — every ``CombatParticipant`` is a PC).
    - ``focused_opponent_target`` → a ``CombatOpponent`` is NPC-only and has
      no ``CharacterSheet`` FK of its own, UNLESS it is a "story NPC" linked
      to a persistent ``scenes.Persona`` (``CombatOpponent.persona``, see
      ``world/combat/escalation.py``'s ``opponent.persona.character_sheet``
      for the same resolution pattern) — that gives a real ``CharacterSheet``
      target-keyed situations can read. A bare (non-persona) NPC opponent
      correctly resolves to ``None``: target-keyed situations (
      ``TARGET_DISTRACTED``/``TARGET_SWAYED_BY_ALLY``/
      ``TARGET_FOCUSED_ELSEWHERE``/``TARGET_FAVORABLY_DISPOSED``) simply
      never hold against it, same as any other targetless cast.

    For a multi-target/AoE cast only this single primary target is resolved
    — per-target perk evaluation for AoE is a legitimate slice-2+
    refinement (see ``vow_situational_power_term``'s docstring).
    """
    if action.focused_opponent_target_id:
        opponent = action.focused_opponent_target
        if opponent.persona_id is not None:
            return opponent.persona.character_sheet
        return None
    if action.focused_ally_target_id:
        return action.focused_ally_target.character_sheet
    return None


def _check_combat_target_prerequisites(
    technique: Technique, caster_od: ObjectDB, targets: list[ObjectDB]
) -> None:
    """Enforce technique.target_prerequisites against combat's explicit target list.

    SINGLE is the only target_type that hard-blocks here: its target list
    (from _build_affected_targets) is the real, complete target set for the
    cast, so a failure hard-blocks the cast — mirroring the non-combat
    SINGLE hard-block in validate_cast_target.

    For target_type=SELF, the caster IS the target — but the real cast dispatcher
    (``_target_spec_for_technique_action`` in ``actions/player_interface.py``) never
    supplies an explicit opponent/ally target for a SELF technique, so
    ``_build_affected_targets`` returns [] (see
    ``test_affected_emitted_for_self_targeted_buff``). Check the caster directly in
    that case rather than relying on targets being populated — mirrors Task 5's
    non-combat SELF fix in ``world/magic/services/targeting.py``.

    AREA/FILTERED_GROUP get NO pre-flight check at all: ``targets`` here is built
    from ``action.focused_opponent_target``, a single FK that for an AoE dispatch
    holds only the arbitrary "first" opponent from a client-supplied
    ``focused_opponent_target_ids`` list (see
    ``RoundContext._resolve_focused_targets``) — not a real single target, and not
    the full AoE set. Hard-blocking the whole cast because THAT one arbitrary
    opponent fails a prerequisite would wrongly kill a cast where other opponents
    in the same AoE set legitimately pass. Defer entirely to
    ``_filter_by_target_prerequisites``'s silent per-opponent filter downstream
    (``_resolved_opponent_targets``, #1793 second-pass fix).
    """
    from actions.constants import ActionTargetType  # noqa: PLC0415
    from world.magic.services.targeting import InvalidCastTarget  # noqa: PLC0415
    from world.mechanics.services import prerequisites_met  # noqa: PLC0415

    prereqs = technique.cached_target_prerequisites
    if not prereqs:
        return

    if technique.target_type in (ActionTargetType.AREA, ActionTargetType.FILTERED_GROUP):
        return

    msg = "Target does not meet this technique's targeting requirement."

    if technique.target_type == ActionTargetType.SELF:
        if not prerequisites_met(prereqs, caster_od, caster_od):
            raise InvalidCastTarget(msg)
        return

    for target_od in targets:
        if not prerequisites_met(prereqs, caster_od, target_od):
            raise InvalidCastTarget(msg)


def combatants_hostile_to(
    actor: CombatParticipant | CombatOpponent,
    *,
    allegiances: dict[int, Allegiance] | None = None,
    opponents: list[CombatOpponent] | None = None,
) -> dict[str, list]:
    """Return the combatants *actor* may attack, grouped by kind (#1584, #4091).

    Reads EFFECTIVE allegiance (stored side composed with allegiance conditions):
    - A PC participant, an ALLY summon or a charmed NPC: hostile to ENEMY and TURNED
      opponents; never to PCs.
    - A TURNED NPC: hostile to other stored-ENEMY opponents still effectively ENEMY.
    - A calmed (NEUTRAL) NPC: hostile to no one.
    - An ENEMY opponent: hostile to PCs and stored ALLY summons only (Decision 3).

    ``opponents`` is the encounter's ACTIVE opponents when the caller already
    holds them (``select_npc_actions`` computes them once per round, #4091 final
    review), so a round with many charmed or turned attackers does not re-query
    them per attacker. Rows are identity-map shared, so one that fled earlier in
    the same pass is dropped by its live status.
    """
    from world.npc_services.allegiance import effective_allegiances  # noqa: PLC0415

    if opponents is None:
        opponents = list(
            CombatOpponent.objects.filter(
                encounter_id=actor.encounter_id, status=OpponentStatus.ACTIVE
            )
        )
    else:
        opponents = [o for o in opponents if o.status == OpponentStatus.ACTIVE]
    if allegiances is None:
        allegiances = effective_allegiances(opponents)
    if isinstance(actor, CombatParticipant):
        side = Allegiance.ALLY_OF_CASTER
    else:
        side = allegiances.get(actor.pk, Allegiance.ENEMY)
    if side == Allegiance.ALLY_OF_CASTER:
        targets = [
            o for o in opponents if allegiances.get(o.pk) in (Allegiance.ENEMY, Allegiance.TURNED)
        ]
        return {"participants": [], "opponents": targets}
    if side == Allegiance.TURNED:
        targets = [
            o
            for o in opponents
            if o.pk != actor.pk
            and o.allegiance == CombatAllegiance.ENEMY
            and allegiances.get(o.pk) == Allegiance.ENEMY
        ]
        return {"participants": [], "opponents": targets}
    if side == Allegiance.NEUTRAL:
        return {"participants": [], "opponents": []}
    active_pcs = list(
        CombatParticipant.objects.filter(
            encounter_id=actor.encounter_id, status=ParticipantStatus.ACTIVE
        )
    )
    allies = [o for o in opponents if o.allegiance == CombatAllegiance.ALLY]
    return {"participants": active_pcs, "opponents": allies}


def _vulnerability_intensity_bonus(action: CombatRoundAction) -> int:
    """Return the break-bar vulnerability intensity bonus if the action's
    target opponent is currently vulnerable, else 0.

    NOT the escalation currency. This is a POWER-ledger term: it rides
    ``use_technique(power_intensity_bonus=...)`` and never touches
    ``CharacterEngagement.intensity_modifier``, which is what the escalation tick
    and every dramatic surge write (``world/combat/escalation.py``). Two different
    "intensity" concepts share the word in this module - see
    ``world/combat/AGENT_GLOSSARY.md``.
    """
    target = action.focused_opponent_target
    if target is None or target.vulnerability_rounds_remaining <= 0:
        return 0
    return target.vulnerability_intensity_bonus


def _ensure_combat_engagement(participant: CombatParticipant) -> None:
    """Ensure the participant's character holds an engagement (combat-owned, #872).

    Existing non-combat engagements are preserved (begin_engagement contract);
    such participants do not tick or spike this encounter.
    """
    from world.mechanics.constants import EngagementType  # noqa: PLC0415
    from world.mechanics.services import begin_engagement  # noqa: PLC0415

    begin_engagement(
        participant.character_sheet.character,
        EngagementType.COMBAT,
        source=participant.encounter,
    )


def _create_participant(
    encounter: CombatEncounter,
    character_sheet: CharacterSheet,
    *,
    covenant_role: CovenantRole | None = None,
    status: str = ParticipantStatus.ACTIVE,
) -> CombatParticipant:
    """Create a CombatParticipant + its engagement, and record the fighter as a
    scene participant (combat participation implies SceneParticipation, #1236)."""
    if covenant_role is None:
        from world.covenants.services import precedence_role_for_combat  # noqa: PLC0415

        covenant_role = precedence_role_for_combat(character_sheet)
    participant = CombatParticipant.objects.create(
        encounter=encounter,
        character_sheet=character_sheet,
        covenant_role=covenant_role,
        status=status,
    )
    _ensure_combat_engagement(participant)

    from world.combat.escalation import check_hated_foe_surges_for_new_participant  # noqa: PLC0415

    check_hated_foe_surges_for_new_participant(participant)

    if encounter.scene_id:
        from world.scenes.interaction_services import ensure_scene_participation  # noqa: PLC0415

        ensure_scene_participation(encounter.scene, character_sheet.character)
    return participant


def add_participant(
    encounter: CombatEncounter,
    character_sheet: CharacterSheet,
    *,
    covenant_role: CovenantRole | None = None,
) -> CombatParticipant:
    """Create a CombatParticipant linking a PC to an encounter.

    When no role is supplied, default to the character's combat-precedence role
    (Battle wins over Durance — Slice E).
    """
    return _create_participant(encounter, character_sheet, covenant_role=covenant_role)


def remove_participant(participant: CombatParticipant) -> None:
    """Remove a participant: status write + combat engagement teardown (#872)."""
    from world.mechanics.constants import EngagementType  # noqa: PLC0415
    from world.mechanics.services import end_engagement  # noqa: PLC0415

    participant.status = ParticipantStatus.REMOVED
    participant.save(update_fields=["status"])
    end_engagement(
        participant.character_sheet.character,
        EngagementType.COMBAT,
        source=participant.encounter,
    )


def acknowledge_encounter_risk(
    encounter: CombatEncounter,
    character_sheet: CharacterSheet,
) -> EncounterRiskAcknowledgement:
    """Idempotently record that a character acknowledged the encounter's risk (#777).

    Called at every voluntary entry: self-join, hostile-cast initiation, and
    consent-accept. The level is snapshotted at first acknowledgement.
    """
    ack, created = EncounterRiskAcknowledgement.objects.get_or_create(
        encounter=encounter,
        character_sheet=character_sheet,
        defaults={"acknowledged_risk_level": encounter.risk_level},
    )
    # #2051: on first entry, warn a solo character entering a BOSS/HERO_KILLER
    # encounter — the stark darkness line, no gate (decision 2).
    if created:
        _maybe_warn_solo_boss_entry(encounter, character_sheet)
    return ack


def _maybe_warn_solo_boss_entry(
    encounter: CombatEncounter,
    character_sheet: CharacterSheet,
) -> None:
    """Send the solo darkness warning if entering a BOSS/HERO_KILLER encounter alone (#2051)."""
    from world.missions.constants import SOLO_DARKNESS_WARNING  # noqa: PLC0415

    has_boss = CombatOpponent.objects.filter(
        encounter=encounter,
        tier__in=(OpponentTier.BOSS, OpponentTier.HERO_KILLER),
        status=OpponentStatus.ACTIVE,
    ).exists()
    if not has_boss:
        return
    # Check if the character is the only active participant (solo).
    active_count = CombatParticipant.objects.filter(
        encounter=encounter,
        status=ParticipantStatus.ACTIVE,
    ).count()
    if active_count > 1:
        return
    character_sheet.character.msg(SOLO_DARKNESS_WARNING)


def join_encounter(
    encounter: CombatEncounter,
    character_sheet: CharacterSheet,
    *,
    covenant_role: CovenantRole | None = None,
) -> CombatParticipant:
    """Allow a PC to join an active combat encounter.

    Can join during DECLARING or BETWEEN_ROUNDS status.
    Raises ValueError if already participating or encounter is completed.
    """
    allowed = {RoundStatus.DECLARING, RoundStatus.BETWEEN_ROUNDS}
    if encounter.status not in allowed:
        msg = "Can only join during declaration or between rounds."
        raise ValueError(msg)

    # Query instead of cache — write path needs fresh data to prevent races.
    # The unique constraint is the real safety net.
    if CombatParticipant.objects.filter(
        encounter=encounter,
        character_sheet=character_sheet,
        status=ParticipantStatus.ACTIVE,
    ).exists():
        msg = "Already participating in this encounter."
        raise ValueError(msg)

    participant = _create_participant(
        encounter, character_sheet, covenant_role=covenant_role, status=ParticipantStatus.ACTIVE
    )
    acknowledge_encounter_risk(encounter, character_sheet)
    return participant
