"""Tests for the wake arc — unconscious recovery (#2287).

SQLite-compatible: ConditionInstances are created directly (not via
apply_condition, which uses a PG-only DISTINCT ON query path).
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.test_helpers import force_check_outcome
from world.conditions.constants import (
    BLEED_OUT_CONDITION_NAME,
    UNCONSCIOUS_CONDITION_NAME,
)
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)
from world.conditions.models import ConditionInstance
from world.conditions.services import SECONDS_PER_ROUND
from world.traits.factories import CheckOutcomeFactory
from world.vitals.factories import CharacterVitalsFactory
from world.vitals.models import VitalsConsequenceConfig
from world.vitals.services import (
    _stamp_unconscious_wake_deadline,
    attempt_wake,
    calculate_wake_difficulty,
)


class CalculateWakeDifficultyTests(TestCase):
    """The wake difficulty formula: injury scales up, elapsed rounds ease."""

    def test_full_health_no_elapsed_is_base(self) -> None:
        config, _ = VitalsConsequenceConfig.objects.get_or_create(pk=1)
        difficulty = calculate_wake_difficulty(health_pct=1.0, rounds_elapsed=0)
        self.assertEqual(difficulty, config.wake_base_difficulty)

    def test_injury_raises_difficulty(self) -> None:
        config, _ = VitalsConsequenceConfig.objects.get_or_create(pk=1)
        difficulty = calculate_wake_difficulty(health_pct=0.1, rounds_elapsed=0)
        expected = config.wake_base_difficulty + 90 * config.wake_scaling_per_percent
        self.assertEqual(difficulty, expected)

    def test_elapsed_rounds_ease_difficulty(self) -> None:
        config, _ = VitalsConsequenceConfig.objects.get_or_create(pk=1)
        at_zero = calculate_wake_difficulty(health_pct=0.5, rounds_elapsed=0)
        at_ten = calculate_wake_difficulty(health_pct=0.5, rounds_elapsed=10)
        self.assertEqual(at_zero - at_ten, 10 * config.wake_ease_per_round)

    def test_difficulty_floors_at_zero(self) -> None:
        difficulty = calculate_wake_difficulty(health_pct=1.0, rounds_elapsed=10_000)
        self.assertEqual(difficulty, 0)


class AttemptWakeTests(TestCase):
    """attempt_wake: roll gating, success/failure, deadline, rate limit."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.vitals = CharacterVitalsFactory(character_sheet=cls.sheet)
        cls.character = cls.sheet.character
        cls.unconscious = ConditionTemplateFactory(name=UNCONSCIOUS_CONDITION_NAME)
        cls.success_outcome = CheckOutcomeFactory(name="Success", success_level=1)
        cls.failure_outcome = CheckOutcomeFactory(name="Failure", success_level=-1)

    def _make_unconscious(self) -> ConditionInstance:
        return ConditionInstanceFactory(target=self.character, condition=self.unconscious)

    def test_not_unconscious_is_not_attempted(self) -> None:
        result = attempt_wake(self.sheet)
        self.assertFalse(result.attempted)
        self.assertFalse(result.woke)

    def test_successful_check_wakes(self) -> None:
        self._make_unconscious()
        with force_check_outcome(self.success_outcome):
            result = attempt_wake(self.sheet)
        self.assertTrue(result.attempted)
        self.assertTrue(result.woke)
        self.assertFalse(
            ConditionInstance.objects.filter(
                target=self.character, condition=self.unconscious
            ).exists()
        )

    def test_failed_check_stays_down_and_rate_limits(self) -> None:
        self._make_unconscious()
        with force_check_outcome(self.failure_outcome):
            first = attempt_wake(self.sheet)
        self.assertTrue(first.attempted)
        self.assertFalse(first.woke)
        # Immediate retry inside the round-equivalent window: no roll.
        second = attempt_wake(self.sheet)
        self.assertFalse(second.attempted)
        self.assertTrue(
            ConditionInstance.objects.filter(
                target=self.character, condition=self.unconscious
            ).exists()
        )

    def test_combat_tick_skips_rate_limit(self) -> None:
        self._make_unconscious()
        with force_check_outcome(self.failure_outcome):
            attempt_wake(self.sheet)
        with force_check_outcome(self.success_outcome):
            result = attempt_wake(self.sheet, in_combat_tick=True)
        self.assertTrue(result.woke)

    def test_guaranteed_deadline_wakes_without_roll(self) -> None:
        instance = self._make_unconscious()
        instance.expires_at = timezone.now() - timedelta(seconds=1)
        instance.save(update_fields=["expires_at"])
        result = attempt_wake(self.sheet)
        self.assertTrue(result.woke)

    def test_dying_blocks_wake(self) -> None:
        self._make_unconscious()
        bleed_out = ConditionTemplateFactory(name=BLEED_OUT_CONDITION_NAME)
        ConditionInstanceFactory(target=self.character, condition=bleed_out)
        result = attempt_wake(self.sheet)
        self.assertFalse(result.attempted)
        self.assertIn("dying", result.message)

    def test_stamp_sets_guaranteed_deadline_once(self) -> None:
        instance = self._make_unconscious()
        config, _ = VitalsConsequenceConfig.objects.get_or_create(pk=1)
        before = timezone.now()
        _stamp_unconscious_wake_deadline(self.sheet)
        instance.refresh_from_db()
        self.assertIsNotNone(instance.expires_at)
        expected_seconds = config.wake_guaranteed_rounds * SECONDS_PER_ROUND
        delta = (instance.expires_at - before).total_seconds()
        self.assertAlmostEqual(delta, expected_seconds, delta=5)
        # Second stamp keeps the original deadline.
        original = instance.expires_at
        _stamp_unconscious_wake_deadline(self.sheet)
        instance.refresh_from_db()
        self.assertEqual(instance.expires_at, original)
