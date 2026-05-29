from django.test import TestCase

from world.conditions.factories import CapabilityTypeFactory


class CapabilityInnateBaselineTests(TestCase):
    def test_innate_baseline_defaults_zero(self) -> None:
        cap = CapabilityTypeFactory(name="force")
        self.assertEqual(cap.innate_baseline, 0)

    def test_innate_baseline_settable(self) -> None:
        cap = CapabilityTypeFactory(name="awareness", innate_baseline=1)
        self.assertEqual(cap.innate_baseline, 1)
