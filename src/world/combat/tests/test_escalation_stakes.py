"""Tests for the stakes escalation leg (#2013): step bonus, initial surge,
and default-curve assignment at encounter creation."""

from unittest.mock import MagicMock

from django.test import TestCase

from world.combat.constants import ParticipantStatus, StakesLevel, SurgeTriggerKind
from world.combat.escalation import apply_escalation_tick, assign_default_escalation_curve
from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
    EscalationCurveFactory,
)
from world.combat.models import DramaticSurgeRecord, StakesEscalationModifier
from world.mechanics.constants import EngagementType
from world.mechanics.engagement import CharacterEngagement
from world.mechanics.services import begin_engagement


def _fake_check_fn(*_args, **_kwargs):
    result = MagicMock()
    result.outcome = None
    return result


class StakesStepBonusTests(TestCase):
    def test_step_bonus_added_to_intensity_step(self):
        StakesEscalationModifier.objects.create(
            stakes_level=StakesLevel.NATIONAL, intensity_step_bonus=2
        )
        curve = EscalationCurveFactory(intensity_step=1, start_round=1)
        encounter = CombatEncounterFactory(
            escalation_curve=curve, stakes_level=StakesLevel.NATIONAL, round_number=1
        )
        participant = CombatParticipantFactory(encounter=encounter, status=ParticipantStatus.ACTIVE)
        character = participant.character_sheet.character
        begin_engagement(character, EngagementType.COMBAT, source=encounter)

        apply_escalation_tick(encounter, check_fn=_fake_check_fn)

        engagement = CharacterEngagement.objects.get(character=character)
        self.assertEqual(engagement.intensity_modifier, 3)  # 1 (curve) + 2 (stakes)

    def test_no_matching_row_is_zero_bonus(self):
        curve = EscalationCurveFactory(intensity_step=1, start_round=1)
        encounter = CombatEncounterFactory(
            escalation_curve=curve, stakes_level=StakesLevel.LOCAL, round_number=1
        )
        participant = CombatParticipantFactory(encounter=encounter, status=ParticipantStatus.ACTIVE)
        character = participant.character_sheet.character
        begin_engagement(character, EngagementType.COMBAT, source=encounter)

        apply_escalation_tick(encounter, check_fn=_fake_check_fn)

        engagement = CharacterEngagement.objects.get(character=character)
        self.assertEqual(engagement.intensity_modifier, 1)


class InitialStakesSurgeTests(TestCase):
    def test_initial_surge_fires_once_across_two_ticks(self):
        StakesEscalationModifier.objects.create(stakes_level=StakesLevel.WORLD, initial_surge=4)
        curve = EscalationCurveFactory(intensity_step=0, start_round=1)
        encounter = CombatEncounterFactory(
            escalation_curve=curve, stakes_level=StakesLevel.WORLD, round_number=1
        )
        participant = CombatParticipantFactory(encounter=encounter, status=ParticipantStatus.ACTIVE)
        character = participant.character_sheet.character
        begin_engagement(character, EngagementType.COMBAT, source=encounter)

        apply_escalation_tick(encounter, check_fn=_fake_check_fn)
        encounter.round_number = 2
        encounter.save(update_fields=["round_number"])
        apply_escalation_tick(encounter, check_fn=_fake_check_fn)

        engagement = CharacterEngagement.objects.get(character=character)
        self.assertEqual(engagement.intensity_modifier, 4)
        self.assertEqual(
            DramaticSurgeRecord.objects.filter(trigger_kind=SurgeTriggerKind.HIGH_STAKES).count(),
            1,
        )


class AssignDefaultEscalationCurveTests(TestCase):
    def test_assigns_when_curve_is_null_and_row_has_default(self):
        curve = EscalationCurveFactory()
        StakesEscalationModifier.objects.create(
            stakes_level=StakesLevel.REGIONAL, default_curve=curve
        )
        encounter = CombatEncounterFactory(escalation_curve=None, stakes_level=StakesLevel.REGIONAL)

        assign_default_escalation_curve(encounter)

        encounter.refresh_from_db()
        self.assertEqual(encounter.escalation_curve_id, curve.pk)

    def test_noop_when_curve_already_set(self):
        curve = EscalationCurveFactory()
        other_curve = EscalationCurveFactory()
        StakesEscalationModifier.objects.create(
            stakes_level=StakesLevel.REGIONAL, default_curve=other_curve
        )
        encounter = CombatEncounterFactory(
            escalation_curve=curve, stakes_level=StakesLevel.REGIONAL
        )

        assign_default_escalation_curve(encounter)

        encounter.refresh_from_db()
        self.assertEqual(encounter.escalation_curve_id, curve.pk)

    def test_noop_when_no_matching_row(self):
        encounter = CombatEncounterFactory(escalation_curve=None, stakes_level=StakesLevel.LOCAL)

        assign_default_escalation_curve(encounter)

        encounter.refresh_from_db()
        self.assertIsNone(encounter.escalation_curve_id)
