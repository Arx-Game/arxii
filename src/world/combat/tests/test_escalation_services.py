"""Tests for the escalation tick + graded control pace check (#872, Task 5)."""

from unittest import mock

from django.test import TestCase

from world.combat.constants import ParticipantStatus
from world.combat.escalation import apply_escalation_tick
from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
    EscalationCurveFactory,
)
from world.mechanics.constants import EngagementType
from world.mechanics.engagement import CharacterEngagement
from world.mechanics.services import begin_engagement


def _fake_check(success_level):
    """Build a perform_check stand-in returning an outcome with success_level."""
    outcome = mock.Mock()
    outcome.success_level = success_level
    result = mock.Mock()
    result.outcome = outcome

    def check_fn(character, check_type, target_difficulty=0, extra_modifiers=0, **kwargs):
        return result

    return check_fn


class EscalationTickTests(TestCase):
    def setUp(self):
        self.curve = EscalationCurveFactory(
            start_round=2,
            intensity_step=2,
            control_step_on_success=2,
            control_step_on_partial=1,
            control_step_on_botch=-1,
            max_escalation_level=0,
        )
        self.encounter = CombatEncounterFactory(escalation_curve=self.curve)
        self.encounter.round_number = 2
        self.encounter.save(update_fields=["round_number"])
        self.participant = CombatParticipantFactory(
            encounter=self.encounter, status=ParticipantStatus.ACTIVE
        )
        self.character = self.participant.character_sheet.character
        begin_engagement(self.character, EngagementType.COMBAT, source=self.encounter)

    def _engagement(self):
        return CharacterEngagement.objects.get(character=self.character)

    def test_tick_bumps_intensity_and_level(self):
        results = apply_escalation_tick(self.encounter, check_fn=_fake_check(1))
        eng = self._engagement()
        self.assertEqual(eng.escalation_level, 1)
        self.assertEqual(eng.intensity_modifier, 2)
        self.assertEqual(eng.control_modifier, 2)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].pace_success_level, 1)

    def test_partial_gains_partial_control(self):
        apply_escalation_tick(self.encounter, check_fn=_fake_check(0))
        self.assertEqual(self._engagement().control_modifier, 1)

    def test_failure_gains_no_control(self):
        apply_escalation_tick(self.encounter, check_fn=_fake_check(-1))
        self.assertEqual(self._engagement().control_modifier, 0)

    def test_botch_loses_control(self):
        apply_escalation_tick(self.encounter, check_fn=_fake_check(-2))
        self.assertEqual(self._engagement().control_modifier, -1)

    def test_no_tick_before_start_round(self):
        self.encounter.round_number = 1
        self.encounter.save(update_fields=["round_number"])
        results = apply_escalation_tick(self.encounter, check_fn=_fake_check(1))
        self.assertEqual(results, [])
        self.assertEqual(self._engagement().escalation_level, 0)

    def test_no_tick_without_curve(self):
        self.encounter.escalation_curve = None
        self.encounter.save(update_fields=["escalation_curve"])
        results = apply_escalation_tick(self.encounter, check_fn=_fake_check(1))
        self.assertEqual(results, [])

    def test_cap_stops_ramp(self):
        self.curve.max_escalation_level = 1
        self.curve.save(update_fields=["max_escalation_level"])
        apply_escalation_tick(self.encounter, check_fn=_fake_check(1))
        results = apply_escalation_tick(self.encounter, check_fn=_fake_check(1))
        eng = self._engagement()
        self.assertEqual(eng.escalation_level, 1)
        self.assertEqual(eng.intensity_modifier, 2)
        self.assertTrue(results[0].capped)

    def test_difficulty_scales_with_level(self):
        captured = []

        def spy_check(character, check_type, target_difficulty=0, extra_modifiers=0, **kwargs):
            captured.append(target_difficulty)
            outcome = mock.Mock()
            outcome.success_level = 1
            result = mock.Mock()
            result.outcome = outcome
            return result

        self.curve.pace_difficulty_base = 10
        self.curve.pace_difficulty_per_level = 5
        self.curve.save(update_fields=["pace_difficulty_base", "pace_difficulty_per_level"])
        apply_escalation_tick(self.encounter, check_fn=spy_check)
        apply_escalation_tick(self.encounter, check_fn=spy_check)
        # level increments before the check: difficulty = base + per_level * level
        self.assertEqual(captured, [15, 20])

    def test_missing_engagement_recreated(self):
        CharacterEngagement.objects.filter(character=self.character).delete()
        results = apply_escalation_tick(self.encounter, check_fn=_fake_check(1))
        self.assertEqual(len(results), 1)
        self.assertEqual(self._engagement().escalation_level, 1)

    def test_noncombat_engagement_skipped(self):
        eng = self._engagement()
        eng.engagement_type = EngagementType.CHALLENGE
        eng.save(update_fields=["engagement_type"])
        results = apply_escalation_tick(self.encounter, check_fn=_fake_check(1))
        self.assertEqual(results, [])
        self.assertEqual(self._engagement().escalation_level, 0)
