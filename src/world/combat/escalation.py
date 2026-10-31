"""Combat escalation engine (#872).

Per-round pressure for opted-in encounters: each escalating round, every ACTIVE
participant's combat engagement gains authored intensity, and a control pace
check decides whether control keeps up. All downstream consequences (anima-cost
spikes, Soulfray, mishap pools, Audere gates) are emergent through the existing
cast pipeline — this module only writes engagement process modifiers.
"""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, Any

from django.contrib.contenttypes.models import ContentType
from django.db.models import F

from world.combat.constants import ParticipantStatus, SurgeTriggerKind
from world.combat.types import DramaticSurgeBeat, EscalationTickResult
from world.mechanics.constants import EngagementType
from world.mechanics.services import begin_engagement

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.combat.models import (
        CombatEncounter,
        CombatOpponent,
        CombatParticipant,
        EscalationCurve,
    )
    from world.combat.types import PerformCheckFn
    from world.companions.models import Companion
    from world.traits.models import CheckOutcome

logger = logging.getLogger(__name__)

DEFAULT_SURGE_NARRATION = "{character}'s power surges with sudden, dramatic force."


def _control_step(curve: EscalationCurve, success_level: int) -> int:
    """Map a pace-check success_level band to the authored control step.

    Banding mirrors outcome_to_delta (clash.py): >=1 success, ==0 partial,
    ==-1 failure (no step), <=-2 botch.
    """
    if success_level >= 1:
        return curve.control_step_on_success
    if success_level == 0:
        return curve.control_step_on_partial
    if success_level == -1:
        return 0
    return curve.control_step_on_botch


def apply_escalation_tick(
    encounter: CombatEncounter,
    *,
    check_fn: PerformCheckFn | None = None,
) -> list[EscalationTickResult]:
    """Run one escalation tick for every ACTIVE participant of ``encounter``.

    No-ops (returns []) when the encounter has no curve or the round has not
    reached ``curve.start_round``. ``check_fn`` overrides ``perform_check``
    for tests.

    Failure consequences are lag-only by design: a widening intensity−control
    deficit bites at the character's next cast through the existing mishap
    pipeline. No mishaps are rolled here.

    Stakes coupling (#2013): ``StakesEscalationModifier.intensity_step_bonus``
    for this encounter's stakes_level is added to every participant's per-tick
    intensity gain; ``initial_surge`` fires once (ever, via
    ``apply_dramatic_surge``'s dedup) as a HIGH_STAKES beat on the first tick
    that actually runs — it shares the ``curve.start_round`` gate above, per
    the spec's "at the first tick round".
    """
    from world.combat.models import CombatParticipant  # noqa: PLC0415
    from world.mechanics.engagement import CharacterEngagement  # noqa: PLC0415

    curve = encounter.escalation_curve
    if curve is None or encounter.round_number < curve.start_round:
        return []

    if check_fn is None:
        from world.checks.services import perform_check  # noqa: PLC0415

        check_fn = perform_check

    encounter_ct = ContentType.objects.get_for_model(encounter)
    results: list[EscalationTickResult] = []
    participants = list(
        CombatParticipant.objects.filter(
            encounter=encounter,
            status=ParticipantStatus.ACTIVE,
        ).select_related("character_sheet__character")
    )
    step_bonus = _stakes_intensity_step_bonus(encounter.stakes_level)

    for participant in participants:
        character = participant.character_sheet.character
        engagement = CharacterEngagement.objects.filter(character_id=character.pk).first()
        if engagement is None:
            logger.warning(
                "Escalation tick: missing engagement for %s in encounter %s; recreating.",
                character,
                encounter.pk,
            )
            engagement = begin_engagement(character, EngagementType.COMBAT, source=encounter)
        if (
            engagement.engagement_type != EngagementType.COMBAT
            or engagement.source_content_type_id != encounter_ct.pk
            or engagement.source_id != encounter.pk
        ):
            # Engaged elsewhere (challenge/mission or another encounter): no tick.
            continue

        capped = (
            curve.max_escalation_level > 0
            and engagement.escalation_level >= curve.max_escalation_level
        )
        pace_success_level: int | None = None
        if not capped:
            engagement.escalation_level += 1
            engagement.intensity_modifier += curve.intensity_step + step_bonus
            difficulty = (
                curve.pace_difficulty_base
                + curve.pace_difficulty_per_level * engagement.escalation_level
            )
            check_result = check_fn(character, curve.pace_check_type, target_difficulty=difficulty)
            outcome = check_result.outcome
            if outcome is not None:
                pace_success_level = outcome.success_level
                engagement.control_modifier += _control_step(curve, pace_success_level)
            engagement.save(
                update_fields=[
                    "escalation_level",
                    "intensity_modifier",
                    "control_modifier",
                ]
            )

        results.append(
            EscalationTickResult(
                participant=participant,
                escalation_level=engagement.escalation_level,
                intensity_modifier=engagement.intensity_modifier,
                control_modifier=engagement.control_modifier,
                pace_success_level=pace_success_level,
                capped=capped,
            )
        )

    _apply_initial_stakes_surge(encounter, participants)

    return results


def _stakes_intensity_step_bonus(stakes_level: str) -> int:
    """The authored intensity_step_bonus for ``stakes_level``, or 0 if unseeded (#2013)."""
    from world.combat.models import StakesEscalationModifier  # noqa: PLC0415

    return (
        StakesEscalationModifier.objects.filter(stakes_level=stakes_level)
        .values_list("intensity_step_bonus", flat=True)
        .first()
        or 0
    )


def _apply_initial_stakes_surge(
    encounter: CombatEncounter,
    participants: list[CombatParticipant],
) -> None:
    """Grant the one-shot HIGH_STAKES surge to every ticked participant (#2013).

    Attempted on every tick — safe because ``apply_dramatic_surge``'s dedup
    makes every call after the first a clean no-op. No-ops entirely when the
    stakes row is unseeded or authored with initial_surge=0.
    """
    from world.combat.models import StakesEscalationModifier  # noqa: PLC0415

    modifier = StakesEscalationModifier.objects.filter(stakes_level=encounter.stakes_level).first()
    if modifier is None or modifier.initial_surge <= 0:
        return
    for participant in participants:
        apply_dramatic_surge(
            encounter=encounter,
            participant=participant,
            amount=modifier.initial_surge,
            trigger_kind=SurgeTriggerKind.HIGH_STAKES,
            subject_sheet=None,
        )


ESCALATION_SPIKE_TRIGGER_NAMES = (
    "escalation_spike_on_incapacitated",
    "escalation_spike_on_killed",
    "escalation_spike_on_mortal_peril",
    "escalation_spike_on_damage",
)


def install_escalation_room_triggers(encounter: CombatEncounter) -> None:
    """Idempotently install the spike triggers on the encounter's room.

    Runs every escalating begin_declaration_phase (covers mid-encounter curve
    assignment). No-ops when the seeded TriggerDefinitions are absent (content
    not wired in this deployment) or the encounter has no room.
    """
    from flows.models import Trigger, TriggerDefinition  # noqa: PLC0415

    room = encounter.room
    if room is None:
        return
    for name in ESCALATION_SPIKE_TRIGGER_NAMES:
        trigger_def = TriggerDefinition.objects.filter(name=name).first()
        if trigger_def is None:
            continue
        trigger, created = Trigger.objects.get_or_create(obj=room, trigger_definition=trigger_def)
        if created:
            handler = room.trigger_handler
            if handler is not None:
                handler.on_trigger_added(trigger)


def remove_escalation_room_triggers(encounter: CombatEncounter) -> None:
    """Remove the room spike triggers unless another live escalating encounter
    shares the room.

    Called from ``cleanup_completed_encounter``, which ``resolve_round`` invokes
    *before* persisting ``status=COMPLETED`` — the ``exclude(pk=...)`` keeps the
    encounter being cleaned from blocking its own removal; other encounters'
    statuses are already persisted and therefore accurate.
    """
    from flows.models import Trigger, TriggerDefinition  # noqa: PLC0415
    from world.combat.models import CombatEncounter  # noqa: PLC0415
    from world.scenes.constants import RoundStatus  # noqa: PLC0415

    room = encounter.room
    if room is None:
        return
    shares_room = (
        CombatEncounter.objects.filter(room=room, escalation_curve__isnull=False)
        .exclude(pk=encounter.pk)
        .exclude(status=RoundStatus.COMPLETED)
        .exists()
    )
    if shares_room:
        return
    defs = TriggerDefinition.objects.filter(name__in=ESCALATION_SPIKE_TRIGGER_NAMES)
    triggers = list(Trigger.objects.filter(obj=room, trigger_definition__in=defs))
    if not triggers:
        return
    trigger_pks = [t.pk for t in triggers]
    Trigger.objects.filter(pk__in=trigger_pks).delete()
    # Invalidate the in-memory TriggerHandler cache so dispatch stops seeing
    # the deleted rows (same sequence as soul_tether's install path).
    handler = room.trigger_handler
    if handler is not None:
        for pk in trigger_pks:
            handler.on_trigger_removed(pk)


def _render_surge_narration(curve: EscalationCurve, character_name: str) -> str:
    """Render the surge narration line, substituting only '{character}'.

    Deliberate substring replace (not str.format): any OTHER brace token an
    authored template might contain (e.g. '{subject}') stays inert literal
    text instead of raising or ever resolving to a real value — the leak
    guard is structural, not a validation rule.
    """
    template = curve.surge_narration or DEFAULT_SURGE_NARRATION
    return template.replace("{character}", character_name)


def apply_dramatic_surge(  # noqa: PLR0913 - keyword-only surge fields, cohesive
    *,
    encounter: CombatEncounter,
    participant: CombatParticipant,
    amount: int,
    trigger_kind: str,
    subject_sheet: CharacterSheet | None = None,
    reason: str = "",
    subject_opponent: CombatOpponent | None = None,
    subject_phase_number: int | None = None,
    subject_companion: Companion | None = None,
    outcome: CheckOutcome | None = None,
    potency: int | None = None,
    control_change: int = 0,
    repeat_round: int | None = None,
    narrate: bool = True,
    cause: str = "",
    vow_scaling: int = 0,
) -> DramaticSurgeBeat | None:
    """Write one dramatic-surge event (#2013): the shared seam every trigger leg uses.

    Guards on the participant's COMBAT engagement being sourced to THIS
    encounter (mirrors ``apply_escalation_tick``'s guard) — no engagement, no
    surge, no record. Dedups via ``DramaticSurgeRecord``'s partial unique
    constraints: a repeat call with the same (encounter, participant,
    trigger_kind, subject_sheet) is a clean no-op (returns None) — nothing is
    written twice. On success: adds ``amount`` to
    ``engagement.intensity_modifier``, broadcasts the generic narration line
    to the encounter's room (telnet + the room's scene log), and returns a
    ``DramaticSurgeBeat`` for inline use.

    ``reason`` (#3387) is GM-stated provenance for a manual (``GM_MANUAL``)
    trigger — every automatic trigger_kind leaves it blank.

    A boss beat (#3445) passes ``subject_opponent`` plus ``subject_phase_number``
    instead of ``subject_sheet``, and dedups on that tuple - one surge per boss
    per phase, so a multi-phase boss surges at each transition while the #2642
    re-break loop cannot repeat itself.

    A companion fall (#3575) passes ``subject_companion`` and dedups on
    (encounter, participant, trigger_kind, subject_companion).

    A rolled surge (#4737) passes ``repeat_round`` (the encounter's round), so the same
    kind and subject can surge again in a later round while the same round still dedups.
    ``outcome`` and ``potency`` are the roll that picked the amount, kept on the record;
    ``control_change`` is added to the engagement's control modifier in the same save.
    ``narrate=False`` skips the room line (a surge whose intensity scaled to 0 would
    announce a power surge that added none). ``cause`` is stored on the record for the
    surged player, GMs and staff to read (#4737); it is never broadcast. ``vow_scaling``
    is the part of ``amount`` a giver's vow added (#4739), written with the record.
    """
    from world.combat.models import (  # noqa: PLC0415
        CombatEncounter as _CombatEncounter,
        DramaticSurgeRecord,
    )
    from world.mechanics.engagement import CharacterEngagement  # noqa: PLC0415

    encounter_ct = ContentType.objects.get_for_model(_CombatEncounter)
    engagement = CharacterEngagement.objects.filter(
        character=participant.character_sheet,
        engagement_type=EngagementType.COMBAT,
        source_content_type=encounter_ct,
        source_id=encounter.pk,
    ).first()
    if engagement is None:
        return None

    record, created = DramaticSurgeRecord.objects.get_or_create(
        encounter=encounter,
        participant=participant,
        trigger_kind=trigger_kind,
        subject_sheet=subject_sheet,
        subject_opponent=subject_opponent,
        subject_phase_number=subject_phase_number,
        subject_companion=subject_companion,
        repeat_round=repeat_round,
        defaults={
            "amount": amount,
            "round_number": encounter.round_number,
            "reason": reason,
            "outcome": outcome,
            "potency": potency,
            "control_change": control_change,
            "cause": cause,
            "vow_scaling": vow_scaling,
        },
    )
    if not created:
        return None

    engagement.intensity_modifier += amount
    updated_fields = ["intensity_modifier"]
    if control_change:
        engagement.control_modifier += control_change
        updated_fields.append("control_modifier")
    engagement.save(update_fields=updated_fields)

    curve = encounter.escalation_curve
    character_name = participant.character_sheet.character.db_key
    narration = (
        _render_surge_narration(curve, character_name) if curve is not None and narrate else ""
    )
    room = encounter.room
    if room is not None and narration:
        room.msg_contents(narration)

    return DramaticSurgeBeat(
        participant=participant,
        trigger_kind=trigger_kind,
        amount=amount,
        narration=narration,
        round_number=encounter.round_number,
        outcome_name=outcome.name if outcome is not None else "",
        potency=potency,
        control_change=control_change,
        record_id=record.pk,
    )


def _active_companion_for(  # noqa: OBJECTDB_PARAM - payload carries ObjectDB
    character: ObjectDB,
) -> Companion | None:
    """The bonded, unreleased ``Companion`` whose live object is ``character`` (#3575).

    None for any other object, so the surge legs treat sheetless non-companions
    (a GM character, a summon) as nothing to surge for.
    """
    return character.companion_rows.filter(released_at__isnull=True).first()


def apply_relationship_escalation_spike(
    *,
    fallen_character: ObjectDB,  # noqa: OBJECTDB_PARAM — payload carries ObjectDB
    room: ObjectDB,  # noqa: OBJECTDB_PARAM — emit location is the room ObjectDB
) -> None:
    """Spike intensity for bonded co-combatants when a character falls (#872).

    Processes every live escalating encounter in ``room`` (zero matches is a
    clean no-op — e.g. a deferred CHARACTER_KILLED firing after completion).
    Control does NOT keep pace with a spike: grief is pure pressure.
    Qualification is one-directional by design: the survivor's own track
    points toward the fallen drive their spike, not the reverse direction.
    A survivor only spikes for the encounter their engagement is sourced to
    (same guard as ``apply_escalation_tick``), so co-located escalating
    encounters cannot double-dip a single fall.

    A bonded companion (#3575) has no sheet: when ``fallen_character`` is a live
    ``CompanionObject`` the bond is read from ``CharacterRelationship.target_companion``
    (same track flag, same point floor) and the record's subject is the companion.
    The ALLY_PERIL leg never fires for a companion: acute peril is BLEED_OUT on the
    participant vitals path, and an opponent goes ACTIVE to DEFEATED with no peril band.
    """
    from world.combat.models import CombatEncounter, CombatParticipant  # noqa: PLC0415
    from world.relationships.models import CharacterRelationship  # noqa: PLC0415
    from world.scenes.constants import RoundStatus  # noqa: PLC0415

    fallen_sheet = fallen_character.character_sheet
    fallen_companion = None
    if fallen_sheet is None:
        fallen_companion = _active_companion_for(fallen_character)
        if fallen_companion is None:
            return

    encounters = CombatEncounter.objects.filter(
        room=room,
        escalation_curve__isnull=False,
    ).exclude(status=RoundStatus.COMPLETED)

    for encounter in encounters:
        curve = encounter.escalation_curve
        participants = CombatParticipant.objects.filter(
            encounter=encounter,
            status=ParticipantStatus.ACTIVE,
        ).select_related("character_sheet__character")
        if fallen_sheet is not None:
            participants = participants.exclude(character_sheet=fallen_sheet)
        for participant in participants:
            bond = (
                CharacterRelationship.objects.filter(
                    source=participant.character_sheet,
                    is_active=True,
                    labels__ended_at__isnull=True,
                    labels__type__fuels_escalation_spikes=True,
                )
                .annotate(_depth=F("scene_depth") + F("invested_depth"))
                .filter(_depth__gte=curve.spike_minimum_track_points)
            )
            if fallen_companion is not None:
                bond = bond.filter(target_companion=fallen_companion)
            else:
                bond = bond.filter(target=fallen_sheet)
            if not bond.exists():
                continue
            apply_dramatic_surge(
                encounter=encounter,
                participant=participant,
                amount=curve.spike_intensity_amount,
                trigger_kind=SurgeTriggerKind.ALLY_FALLEN,
                subject_sheet=fallen_sheet,
                subject_companion=fallen_companion,
            )


def relationship_spike_handler(*, payload: Any) -> None:
    """Flow-callable subscriber for CHARACTER_INCAPACITATED / CHARACTER_KILLED.

    Seeded TriggerDefinitions (``wire_escalation_content``) dispatch here via
    a CALL_SERVICE_FUNCTION step with the event payload.
    """
    character = payload.character
    room = character.location
    if room is None:
        return
    apply_relationship_escalation_spike(fallen_character=character, room=room)


def apply_peril_escalation_spike(
    *,
    victim_character: ObjectDB,  # noqa: OBJECTDB_PARAM — payload carries ObjectDB
    room: ObjectDB,  # noqa: OBJECTDB_PARAM — emit location is the room ObjectDB
) -> None:
    """Spike intensity for bonded co-combatants when an ally enters mortal peril (#2013).

    Mirrors ``apply_relationship_escalation_spike`` exactly, except: fires on
    the victim ENTERING an acute-peril condition (not falling), reads
    ``curve.peril_spike_intensity_amount``, and tags the record
    ``SurgeTriggerKind.ALLY_PERIL``. Dedup (one surge per victim per
    encounter, even across a re-applied/stacked condition) is enforced by
    ``DramaticSurgeRecord``'s unique constraint via ``apply_dramatic_surge`` —
    no separate one-shot bookkeeping needed here.
    """
    from world.combat.models import CombatEncounter, CombatParticipant  # noqa: PLC0415
    from world.relationships.models import CharacterRelationship  # noqa: PLC0415
    from world.scenes.constants import RoundStatus  # noqa: PLC0415

    victim_sheet = victim_character.character_sheet
    if victim_sheet is None:
        return

    encounters = CombatEncounter.objects.filter(
        room=room,
        escalation_curve__isnull=False,
    ).exclude(status=RoundStatus.COMPLETED)

    for encounter in encounters:
        curve = encounter.escalation_curve
        participants = (
            CombatParticipant.objects.filter(
                encounter=encounter,
                status=ParticipantStatus.ACTIVE,
            )
            .exclude(character_sheet=victim_sheet)
            .select_related("character_sheet__character")
        )
        for participant in participants:
            qualifies = (
                CharacterRelationship.objects.filter(
                    source=participant.character_sheet,
                    target=victim_sheet,
                    is_active=True,
                    labels__ended_at__isnull=True,
                    labels__type__fuels_escalation_spikes=True,
                )
                .annotate(_depth=F("scene_depth") + F("invested_depth"))
                .filter(_depth__gte=curve.spike_minimum_track_points)
                .exists()
            )
            if not qualifies:
                continue
            apply_dramatic_surge(
                encounter=encounter,
                participant=participant,
                amount=curve.peril_spike_intensity_amount,
                trigger_kind=SurgeTriggerKind.ALLY_PERIL,
                subject_sheet=victim_sheet,
            )


def peril_spike_handler(*, payload: Any) -> None:
    """Flow-callable subscriber for CONDITION_APPLIED (#2013).

    Filters to the acute-peril condition names (reuses
    ``acute_peril_condition_ids``, so it doesn't duplicate the list) before doing
    any relationship read, mirroring ``relationship_spike_handler``'s shape.
    """
    from world.vitals.peril_resolution import acute_peril_condition_ids  # noqa: PLC0415

    if payload.instance.condition_id not in acute_peril_condition_ids():
        return
    room = payload.target.location
    if room is None:
        return
    apply_peril_escalation_spike(victim_character=payload.target, room=room)


def qualifying_bond_depths(
    sources: list[CharacterSheet],
    target_sheet: CharacterSheet,
    encounter: CombatEncounter,
) -> dict[int, int]:
    """Each source sheet's deepest qualifying bond to ``target_sheet``, by sheet pk (#4737).

    One query. A bond qualifies when it is active, carries a live label whose type fuels
    escalation spikes, and is at least the encounter's spike minimum deep (scene plus
    invested depth). Sources with no qualifying bond are absent, and an encounter with no
    escalation curve has none. Both the hurt-ally surge
    and a steadying ally read bond depth through this one filter (#4802).
    """
    from world.relationships.models import CharacterRelationship  # noqa: PLC0415

    curve = encounter.escalation_curve
    if curve is None:
        return {}
    depth_by_sheet: dict[int, int] = {}
    bonds = (
        CharacterRelationship.objects.filter(
            source__in=sources,
            target=target_sheet,
            is_active=True,
            labels__ended_at__isnull=True,
            labels__type__fuels_escalation_spikes=True,
        )
        .annotate(_depth=F("scene_depth") + F("invested_depth"))
        .filter(_depth__gte=curve.spike_minimum_track_points)
        .values_list("source_id", "_depth")
    )
    for source_id, depth in bonds:
        depth_by_sheet[source_id] = max(depth, depth_by_sheet.get(source_id, 0))
    return depth_by_sheet


def _hurt_ally_rollers(
    encounter: CombatEncounter,
    victim_sheet: CharacterSheet,
) -> list[tuple[CombatParticipant, int]]:
    """The participants who roll for a hurt ``victim_sheet`` this round, with bond depth (#4737).

    Four queries for the whole encounter whatever its size: its active participants, their
    qualifying bonds to the victim, the surge rows already written this round, and the
    COMBAT engagements sourced to this encounter. A participant rolls only when they have a
    qualifying bond (the peril-leg rule), have not surged for this victim this round, and
    have the engagement ``apply_dramatic_surge`` needs, so a roll that could not surge never
    spends a contributing condition.
    """
    from world.combat.models import (  # noqa: PLC0415
        CombatEncounter as _CombatEncounter,
        CombatParticipant,
        DramaticSurgeRecord,
    )
    from world.mechanics.engagement import CharacterEngagement  # noqa: PLC0415

    participants = list(
        CombatParticipant.objects.filter(encounter=encounter, status=ParticipantStatus.ACTIVE)
        .exclude(character_sheet=victim_sheet)
        .select_related("character_sheet__character")
    )
    if not participants:
        return []
    depth_by_sheet = qualifying_bond_depths(
        [p.character_sheet for p in participants], victim_sheet, encounter
    )
    candidates = [p for p in participants if p.character_sheet_id in depth_by_sheet]
    if not candidates:
        return []
    # Must mirror apply_dramatic_surge's dedup key (encounter, participant, kind,
    # subject_sheet, repeat_round); a row here means this hit would be swallowed there.
    surged = set(
        DramaticSurgeRecord.objects.filter(
            encounter=encounter,
            trigger_kind=SurgeTriggerKind.ALLY_HURT,
            repeat_round=encounter.round_number,
            subject_sheet=victim_sheet,
        ).values_list("participant_id", flat=True)
    )
    engaged = set(
        CharacterEngagement.objects.filter(
            character__in=[p.character_sheet for p in candidates],
            engagement_type=EngagementType.COMBAT,
            source_content_type=ContentType.objects.get_for_model(_CombatEncounter),
            source_id=encounter.pk,
        ).values_list("character_id", flat=True)
    )
    return [
        (p, depth_by_sheet[p.character_sheet_id])
        for p in candidates
        if p.pk not in surged and p.character_sheet_id in engaged
    ]


def apply_ally_hurt_surge(
    *,
    victim_character: ObjectDB,  # noqa: OBJECTDB_PARAM - payload carries ObjectDB
    room: ObjectDB,  # noqa: OBJECTDB_PARAM - emit location is the room ObjectDB
    damage: int,
    max_health: int,
) -> None:
    """Roll a rolled surge for each bonded co-combatant of a hurt ally (#4737).

    Qualification mirrors ``apply_peril_escalation_spike`` (an open relationship label of a
    ``fuels_escalation_spikes`` type, depth at or above the curve's
    ``spike_minimum_track_points``, never the victim). Each qualifying player character
    rolls the authored ``ALLY_HURT`` check against a difficulty of
    ``potency_base + potency_per_depth * depth``; the band the outcome picks is scaled by
    the wound (``damage / max_health``, at most 1) and written through ``apply_rolled_surge``.
    Dedup is per round per ally in the surge record, so a second hit on the same ally in
    the same round does nothing, and the roll is skipped when that row already exists or the
    participant has no COMBAT engagement sourced to the encounter (``_hurt_ally_rollers``).

    DAMAGE_APPLIED fires on every hit, so the cheap exits (no damage, no sheet, no live
    escalating encounter, no tuning) all come before any per-participant query, and the
    tuning is read quietly (a row staff have not authored yet is not a per-hit log line). An
    exception from the surge write is not caught: it is atomic and a swallowed failure
    would leave the cached engagement stale.
    """
    from world.combat.models import CombatEncounter  # noqa: PLC0415
    from world.combat.surge_rolls import (  # noqa: PLC0415
        apply_rolled_surge,
        surge_roll_for_participant,
        surge_tuning_for,
    )
    from world.scenes.constants import RoundStatus  # noqa: PLC0415
    from world.scenes.services import persona_names_for_sheets  # noqa: PLC0415

    if damage <= 0 or max_health <= 0:
        return
    victim_sheet = victim_character.character_sheet
    if victim_sheet is None:
        return
    encounters = list(
        CombatEncounter.objects.filter(room=room, escalation_curve__isnull=False)
        .exclude(status=RoundStatus.COMPLETED)
        .select_related("escalation_curve")
    )
    if not encounters:
        return
    # Quiet: an unauthored row is not worth a log line on every hit.
    tuning = surge_tuning_for(SurgeTriggerKind.ALLY_HURT, warn=False)
    if tuning is None:
        return
    wound = min(1.0, damage / max_health)
    # Half up, at most 100: the percent of their health the ally lost, in the cause line.
    percent = min(100, math.floor(wound * 100 + 0.5))
    ally_name = persona_names_for_sheets([victim_sheet.pk]).get(
        victim_sheet.pk, victim_character.key
    )

    for encounter in encounters:
        rollers = _hurt_ally_rollers(encounter, victim_sheet)
        # One persona lookup for the surged players of this encounter (never a query each).
        surged_names = persona_names_for_sheets(p.character_sheet_id for p, _ in rollers)
        for participant, depth in rollers:
            surged_name = surged_names.get(
                participant.character_sheet_id, participant.character_sheet.character.key
            )
            cause = f"{ally_name}, bonded to {surged_name}, loses {percent}% of their health."
            potency = tuning.potency_base + tuning.potency_per_depth * depth
            result = surge_roll_for_participant(participant, tuning.check_type, potency)
            apply_rolled_surge(
                encounter=encounter,
                participant=participant,
                trigger_kind=SurgeTriggerKind.ALLY_HURT,
                outcome=result.outcome,
                potency=potency,
                subject_sheet=victim_sheet,
                intensity_scale=wound,
                tuning=tuning,
                cause=cause,
            )


def ally_hurt_spike_handler(*, payload: Any) -> None:
    """Flow-callable subscriber for DAMAGE_APPLIED (#4737).

    The wound is the damage actually dealt this hit (``amount_dealt``) against the
    victim's ``CharacterVitals.max_health``. Exits before any vitals read when nothing
    was dealt or the victim is nowhere.
    """
    from world.vitals.models import CharacterVitals  # noqa: PLC0415

    if payload.amount_dealt <= 0:
        return
    victim = payload.target
    room = victim.location
    sheet = victim.character_sheet
    if room is None or sheet is None:
        return
    max_health = (
        CharacterVitals.objects.filter(character_sheet=sheet)
        .values_list("max_health", flat=True)
        .first()
    )
    if not max_health:
        return
    apply_ally_hurt_surge(
        victim_character=victim,
        room=room,
        damage=payload.amount_dealt,
        max_health=max_health,
    )


def _maybe_surge_hated_foe(
    *,
    encounter: CombatEncounter,
    participant: CombatParticipant,
    subject_sheet: CharacterSheet,
    curve: EscalationCurve,
) -> None:
    """Shared qualification + write for one (PC, hated-NPC) pair (#2013).

    Deliberately has NO spike_minimum_track_points floor (unlike the
    grief/peril legs) — decisions 4-6 gate hated-foe only on valence + the
    fuels_escalation_spikes flag.
    """
    from world.relationships.constants import TypeValence  # noqa: PLC0415
    from world.relationships.models import CharacterRelationship  # noqa: PLC0415

    qualifies = CharacterRelationship.objects.filter(
        source=participant.character_sheet,
        target=subject_sheet,
        is_active=True,
        labels__ended_at__isnull=True,
        labels__type__fuels_escalation_spikes=True,
        labels__type__valence=TypeValence.HOSTILE,
    ).exists()
    if not qualifies:
        return
    apply_dramatic_surge(
        encounter=encounter,
        participant=participant,
        amount=curve.hated_foe_spike_intensity_amount,
        trigger_kind=SurgeTriggerKind.HATED_FOE,
        subject_sheet=subject_sheet,
    )


def check_hated_foe_surges_for_new_opponent(opponent: CombatOpponent) -> None:
    """Check every ACTIVE PC against a newly-added NPC opponent (#2013).

    Called from ``add_opponent``. No-op when the encounter has no curve, the
    opponent isn't ENEMY-allegiance, or it has no persona (every PC duel
    mirror and persona-less mook — the common case — has persona=None, so
    this guard alone enforces decision 6: no surge off a hostile PC).
    """
    from world.combat.constants import CombatAllegiance  # noqa: PLC0415
    from world.combat.models import CombatParticipant  # noqa: PLC0415

    encounter = opponent.encounter
    curve = encounter.escalation_curve
    if curve is None:
        return
    if opponent.allegiance != CombatAllegiance.ENEMY or opponent.persona_id is None:
        return
    subject_sheet = opponent.persona.character_sheet
    participants = CombatParticipant.objects.filter(
        encounter=encounter,
        status=ParticipantStatus.ACTIVE,
    ).select_related("character_sheet__character")
    for participant in participants:
        _maybe_surge_hated_foe(
            encounter=encounter, participant=participant, subject_sheet=subject_sheet, curve=curve
        )


def check_hated_foe_surges_for_new_participant(participant: CombatParticipant) -> None:
    """Check a newly-joined PC against every already-present ENEMY opponent (#2013).

    Called from ``_create_participant`` (shared by ``add_participant`` and
    ``join_encounter``). No-op when the encounter has no curve.
    """
    from world.combat.constants import CombatAllegiance, OpponentStatus  # noqa: PLC0415
    from world.combat.models import CombatOpponent  # noqa: PLC0415

    encounter = participant.encounter
    curve = encounter.escalation_curve
    if curve is None:
        return
    opponents = CombatOpponent.objects.filter(
        encounter=encounter,
        status=OpponentStatus.ACTIVE,
        allegiance=CombatAllegiance.ENEMY,
        persona__isnull=False,
    ).select_related("persona__character_sheet")
    for opponent in opponents:
        _maybe_surge_hated_foe(
            encounter=encounter,
            participant=participant,
            subject_sheet=opponent.persona.character_sheet,
            curve=curve,
        )


def assign_default_escalation_curve(encounter: CombatEncounter) -> None:
    """Assign the stakes-authored default curve when the encounter has none (#2013).

    No-op when ``encounter.escalation_curve`` is already set (explicit GM
    authoring always wins) or when the encounter's ``stakes_level`` has no
    ``StakesEscalationModifier`` row, or that row has no ``default_curve``.
    Called once, right after a ``CombatEncounter`` is created — the web
    ``CombatEncounterViewSet.perform_create``, the two duel-seed functions
    (``world.combat.duels``), and hostile-cast encounter seeding
    (``world.combat.cast_seed.seed_or_feed_encounter_from_cast``) — this is
    how a high-stakes fight becomes escalating (and surging) without GM
    micro-setup.
    """
    if encounter.escalation_curve_id is not None:
        return
    from world.combat.models import StakesEscalationModifier  # noqa: PLC0415

    modifier = (
        StakesEscalationModifier.objects.filter(stakes_level=encounter.stakes_level)
        .select_related("default_curve")
        .first()
    )
    if modifier is None or modifier.default_curve_id is None:
        return
    encounter.escalation_curve = modifier.default_curve
    encounter.save(update_fields=["escalation_curve"])


def _surge_every_active_participant(
    *,
    encounter: CombatEncounter,
    opponent: CombatOpponent,
    amount: int,
    trigger_kind: str,
) -> None:
    """Write one boss-beat surge per ACTIVE participant of ``encounter`` (#3445).

    Unlike the grief/peril/hated-foe legs there is no relationship qualification:
    a boss changing phase, enraging, or its wall breaking is public, room-wide
    fact, so it lands on everyone still standing (decision 2) - the same shape as
    ``_apply_initial_stakes_surge``'s HIGH_STAKES leg. An authored amount of 0
    switches the beat off for the curve, mirroring the interference leg's guard
    (``engagement_locks.py``).
    """
    from world.combat.models import CombatParticipant  # noqa: PLC0415

    if amount <= 0:
        return
    participants = CombatParticipant.objects.filter(
        encounter=encounter,
        status=ParticipantStatus.ACTIVE,
    ).select_related("character_sheet__character")
    for participant in participants:
        apply_dramatic_surge(
            encounter=encounter,
            participant=participant,
            amount=amount,
            trigger_kind=trigger_kind,
            subject_sheet=None,
            subject_opponent=opponent,
            subject_phase_number=opponent.current_phase,
        )


def apply_boss_phase_surge(*, opponent: CombatOpponent, enraged: bool) -> None:
    """Surge every ACTIVE PC when a boss crosses into a new phase (#3445).

    ``enraged`` is decided at the seam (``check_and_advance_boss_phase``) by
    comparing the new phase's ``damage_multiplier`` against the one the boss
    carried in. The two kinds are mutually exclusive, so one transition is always
    exactly one surge. Curve-gated per ADR-0098: an encounter with no
    ``escalation_curve`` surges nobody.
    """
    encounter = opponent.encounter
    curve = encounter.escalation_curve
    if curve is None:
        return
    if enraged:
        amount = curve.boss_enrage_spike_intensity_amount
        trigger_kind = SurgeTriggerKind.BOSS_ENRAGE
    else:
        amount = curve.boss_phase_spike_intensity_amount
        trigger_kind = SurgeTriggerKind.BOSS_PHASE
    _surge_every_active_participant(
        encounter=encounter,
        opponent=opponent,
        amount=amount,
        trigger_kind=trigger_kind,
    )


def apply_boss_break_surge(*, opponent: CombatOpponent) -> None:
    """Surge every ACTIVE PC when a boss's break bar reaches zero (#3445).

    Called on every round the bar reads zero, which after the first break is
    every round a qualifying feed lands (#2642 leaves the bar at zero and
    re-opens the vulnerability window). Only the first break in a phase writes
    anything: the dedup key carries ``opponent.current_phase``, so the repeats
    are clean no-ops and a later phase - which re-stamps the bar - surges again.
    """
    encounter = opponent.encounter
    curve = encounter.escalation_curve
    if curve is None:
        return
    _surge_every_active_participant(
        encounter=encounter,
        opponent=opponent,
        amount=curve.boss_break_spike_intensity_amount,
        trigger_kind=SurgeTriggerKind.BOSS_BREAK,
    )
