"""Combat escalation engine (#872).

Per-round pressure for opted-in encounters: each escalating round, every ACTIVE
participant's combat engagement gains authored intensity, and a control pace
check decides whether control keeps up. All downstream consequences (anima-cost
spikes, Soulfray, mishap pools, Audere gates) are emergent through the existing
cast pipeline — this module only writes engagement process modifiers.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.contrib.contenttypes.models import ContentType

from world.combat.constants import ParticipantStatus
from world.combat.types import EscalationTickResult
from world.mechanics.constants import EngagementType
from world.mechanics.services import begin_engagement

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.combat.models import CombatEncounter, EscalationCurve
    from world.combat.types import PerformCheckFn

logger = logging.getLogger(__name__)


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
    participants = CombatParticipant.objects.filter(
        encounter=encounter,
        status=ParticipantStatus.ACTIVE,
    ).select_related("character_sheet__character")

    for participant in participants:
        character = participant.character_sheet.character
        engagement = CharacterEngagement.objects.filter(character=character).first()
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
            engagement.intensity_modifier += curve.intensity_step
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

    return results


ESCALATION_SPIKE_TRIGGER_NAMES = (
    "escalation_spike_on_incapacitated",
    "escalation_spike_on_killed",
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
            handler = getattr(room, "trigger_handler", None)  # noqa: GETATTR_LITERAL
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
    from world.combat.constants import EncounterStatus  # noqa: PLC0415
    from world.combat.models import CombatEncounter  # noqa: PLC0415

    room = encounter.room
    if room is None:
        return
    shares_room = (
        CombatEncounter.objects.filter(room=room, escalation_curve__isnull=False)
        .exclude(pk=encounter.pk)
        .exclude(status=EncounterStatus.COMPLETED)
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
    handler = getattr(room, "trigger_handler", None)  # noqa: GETATTR_LITERAL
    if handler is not None:
        for pk in trigger_pks:
            handler.on_trigger_removed(pk)


def apply_relationship_escalation_spike(
    *,
    fallen_character: ObjectDB,  # noqa: OBJECTDB_PARAM — payload carries ObjectDB
    room: ObjectDB,  # noqa: OBJECTDB_PARAM — emit location is the room ObjectDB
) -> None:
    """Spike intensity for bonded co-combatants when a character falls (#872).

    Processes every live escalating encounter in ``room`` (zero matches is a
    clean no-op — e.g. a deferred CHARACTER_KILLED firing after completion).
    Control does NOT keep pace with a spike: grief is pure pressure.
    """
    from world.combat.constants import EncounterStatus  # noqa: PLC0415
    from world.combat.models import CombatEncounter, CombatParticipant  # noqa: PLC0415
    from world.mechanics.engagement import CharacterEngagement  # noqa: PLC0415
    from world.relationships.models import CharacterRelationship  # noqa: PLC0415

    fallen_sheet = getattr(fallen_character, "sheet_data", None)  # noqa: GETATTR_LITERAL
    if fallen_sheet is None:
        return

    encounters = CombatEncounter.objects.filter(
        room=room,
        escalation_curve__isnull=False,
    ).exclude(status=EncounterStatus.COMPLETED)

    for encounter in encounters:
        curve = encounter.escalation_curve
        participants = (
            CombatParticipant.objects.filter(
                encounter=encounter,
                status=ParticipantStatus.ACTIVE,
            )
            .exclude(character_sheet=fallen_sheet)
            .select_related("character_sheet__character")
        )
        for participant in participants:
            qualifies = CharacterRelationship.objects.filter(
                source=participant.character_sheet,
                target=fallen_sheet,
                is_active=True,
                is_pending=False,
                track_progress__track__fuels_escalation_spikes=True,
                track_progress__developed_points__gte=curve.spike_minimum_track_points,
            ).exists()
            if not qualifies:
                continue
            engagement = CharacterEngagement.objects.filter(
                character=participant.character_sheet.character,
                engagement_type=EngagementType.COMBAT,
            ).first()
            if engagement is None:
                continue
            engagement.intensity_modifier += curve.spike_intensity_amount
            engagement.save(update_fields=["intensity_modifier"])


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
