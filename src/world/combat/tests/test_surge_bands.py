"""Monotonic validation of surge degree bands (#4737)."""

from django.test import TestCase

from world.combat.constants import SurgeTriggerKind
from world.combat.factories import SurgeDegreeBandFactory, SurgeTuningFactory
from world.combat.surge_bands import check_stored_surge_bands, validate_surge_bands
from world.conditions.factories import ConditionTemplateFactory
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
