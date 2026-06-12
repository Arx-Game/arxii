"""Combat escalation engine (#872).

Per-round pressure for opted-in encounters: each escalating round, every ACTIVE
participant's combat engagement gains authored intensity, and a control pace
check decides whether control keeps up. All downstream consequences (anima-cost
spikes, Soulfray, mishap pools, Audere gates) are emergent through the existing
cast pipeline — this module only writes engagement process modifiers.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.contrib.contenttypes.models import ContentType

from world.combat.constants import ParticipantStatus
from world.combat.types import EscalationTickResult
from world.mechanics.constants import EngagementType
from world.mechanics.services import begin_engagement

if TYPE_CHECKING:
    from collections.abc import Callable

    from world.combat.models import CombatEncounter, EscalationCurve

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
    check_fn: Callable | None = None,
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
            outcome = getattr(check_result, "outcome", None)
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
