"""Monotonic validation of surge degree bands (#4737).

Kept: a pure validator with branches; the admin reaches it only through a form."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.combat.constants import SurgeTriggerKind
from world.combat.factories import SurgeDegreeBandFactory, SurgeTuningFactory
from world.combat.surge_bands import check_stored_surge_bands, validate_surge_bands
from world.conditions.factories import ConditionStageFactory, ConditionTemplateFactory
from world.traits.factories import CheckOutcomeFactory


class SurgeBandMonotonicTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.tuning = SurgeTuningFactory(trigger_kind=SurgeTriggerKind.TAUNT_RECEIVED)
        cls.worse = CheckOutcomeFactory(name="Surge Worse", success_level=-1)
        cls.better = CheckOutcomeFactory(name="Surge Better", success_level=2)

    def _band(self, outcome, **kwargs):
        return SurgeDegreeBandFactory.build(tuning=self.tuning, outcome=outcome, **kwargs)

    def test_monotonic_rejects_lower_intensity_at_better_outcome(self) -> None:
        bands = [
            self._band(self.worse, intensity=5, control_change=0),
            self._band(self.better, intensity=2, control_change=0),
        ]
        problems = validate_surge_bands(bands)
        self.assertEqual(len(problems), 1)
        self.assertIn("intensity", problems[0])

    def test_monotonic_rejects_lower_control_at_better_outcome(self) -> None:
        bands = [
            self._band(self.worse, intensity=1, control_change=1),
            self._band(self.better, intensity=3, control_change=-1),
        ]
        problems = validate_surge_bands(bands)
        self.assertEqual(len(problems), 1)
        self.assertIn("control", problems[0])

    def test_monotonic_rejects_condition_only_on_better_outcome(self) -> None:
        goaded = ConditionTemplateFactory(name="Goaded Test")
        bands = [
            self._band(self.worse, intensity=1, control_change=0),
            self._band(self.better, intensity=3, control_change=0, condition=goaded),
        ]
        problems = validate_surge_bands(bands)
        self.assertEqual(len(problems), 1)
        self.assertIn("condition", problems[0])

    def test_monotonic_allows_equal_rows(self) -> None:
        goaded = ConditionTemplateFactory(name="Goaded Equal Test")
        bands = [
            self._band(self.worse, intensity=2, control_change=-1, condition=goaded),
            self._band(self.better, intensity=2, control_change=-1, condition=goaded),
        ]
        self.assertEqual(validate_surge_bands(bands), [])

    def test_monotonic_allows_condition_only_on_worse_outcome(self) -> None:
        goaded = ConditionTemplateFactory(name="Goaded Worse Test")
        bands = [
            self._band(self.worse, intensity=1, control_change=-2, condition=goaded),
            self._band(self.better, intensity=3, control_change=1),
        ]
        self.assertEqual(validate_surge_bands(bands), [])

    def test_monotonic_compares_across_a_tied_success_level(self) -> None:
        tied = CheckOutcomeFactory(name="Surge Tied", success_level=2)
        bands = [
            self._band(self.worse, intensity=5, control_change=0),
            self._band(self.better, intensity=6, control_change=0),
            self._band(tied, intensity=2, control_change=0),
        ]
        problems = validate_surge_bands(bands)
        self.assertEqual(len(problems), 1)
        self.assertIn("Surge Tied", problems[0])
        self.assertIn("Surge Worse", problems[0])

    def test_monotonic_does_not_compare_bands_at_the_same_level(self) -> None:
        tied = CheckOutcomeFactory(name="Surge Tied Peer", success_level=2)
        bands = [
            self._band(self.better, intensity=6, control_change=0),
            self._band(tied, intensity=2, control_change=0),
        ]
        self.assertEqual(validate_surge_bands(bands), [])

    def test_check_stored_bands_reports_bad_rows(self) -> None:
        SurgeDegreeBandFactory(tuning=self.tuning, outcome=self.worse, intensity=5)
        SurgeDegreeBandFactory(tuning=self.tuning, outcome=self.better, intensity=1)
        problems = check_stored_surge_bands()
        self.assertEqual(len(problems), 1)

    def test_check_stored_bands_clean_when_monotonic(self) -> None:
        SurgeDegreeBandFactory(tuning=self.tuning, outcome=self.worse, intensity=1)
        SurgeDegreeBandFactory(tuning=self.tuning, outcome=self.better, intensity=4)
        self.assertEqual(check_stored_surge_bands(), [])


class FeedingConditionBandTests(TestCase):
    """A condition that feeds intensity is a benefit and never sits on a failed roll (#4739)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.tuning = SurgeTuningFactory(trigger_kind=SurgeTriggerKind.RALLIED)
        cls.failure = CheckOutcomeFactory(name="Feed Failure", success_level=-1)
        cls.partial = CheckOutcomeFactory(name="Feed Partial", success_level=0)
        cls.success = CheckOutcomeFactory(name="Feed Success", success_level=1)
        cls.great = CheckOutcomeFactory(name="Feed Great", success_level=2)
        cls.anger = ConditionTemplateFactory(name="Feed Anger", has_progression=True)
        ConditionStageFactory(condition=cls.anger, stage_order=1, intensity_per_round=2)
        cls.goaded = ConditionTemplateFactory(name="Feed Goaded")

    def _band(self, outcome, **kwargs):
        return SurgeDegreeBandFactory.build(
            tuning=self.tuning, outcome=outcome, intensity=1, **kwargs
        )

    def test_a_failed_roll_cannot_carry_a_feeding_condition(self) -> None:
        for outcome in (self.failure, self.partial):
            with self.subTest(outcome=outcome.name):
                problems = validate_surge_bands([self._band(outcome, condition=self.anger)])
                self.assertEqual(len(problems), 1)
                self.assertIn("failed roll", problems[0])
                self.assertIn("Feed Anger", problems[0])

    def test_a_feeding_condition_is_a_benefit_on_a_better_outcome(self) -> None:
        bands = [
            self._band(self.partial),
            self._band(self.success, condition=self.anger),
        ]
        self.assertEqual(validate_surge_bands(bands), [])

    def test_a_better_outcome_cannot_drop_a_feeding_condition(self) -> None:
        bands = [
            self._band(self.success, condition=self.anger),
            self._band(self.great),
        ]
        problems = validate_surge_bands(bands)
        self.assertEqual(len(problems), 1)
        self.assertIn("drop", problems[0])

    def test_a_debuff_is_still_a_cost_above_a_feeding_band(self) -> None:
        bands = [
            self._band(self.success, condition=self.anger),
            self._band(self.great, condition=self.goaded),
        ]
        problems = validate_surge_bands(bands)
        self.assertTrue(any("lacks" in line for line in problems), problems)

    def test_passed_feeding_ids_are_used_without_a_query(self) -> None:
        bands = [self._band(self.success, condition=self.goaded)]
        with self.assertNumQueries(0):
            problems = validate_surge_bands(bands, feeding_condition_ids={self.goaded.pk})
        self.assertEqual(problems, [])

    def test_model_clean_refuses_a_failure_band_carrying_a_feeding_condition(self) -> None:
        band = self._band(self.failure, condition=self.anger)
        with self.assertRaises(ValidationError):
            band.full_clean()

    def test_check_stored_bands_reports_a_feeding_condition_on_a_failure(self) -> None:
        SurgeDegreeBandFactory(
            tuning=self.tuning, outcome=self.failure, intensity=1, condition=self.anger
        )
        problems = check_stored_surge_bands()
        self.assertEqual(len(problems), 1)
        self.assertIn("failed roll", problems[0])
