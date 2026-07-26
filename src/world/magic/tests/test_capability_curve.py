"""Tests for the geometric capability magnitude curve (#2708)."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.magic.models import CapabilityPowerConfig
from world.magic.services.capability_curve import apply_capability_curve


class CapabilityCurveDisabledTests(TestCase):
    """With no config row the curve is inert and returns base unchanged."""

    def test_no_config_row_returns_base(self) -> None:
        self.assertEqual(apply_capability_curve(5, power=50, sensitivity=Decimal("1.0")), 5)

    def test_no_config_row_ignores_sensitivity(self) -> None:
        self.assertEqual(apply_capability_curve(9, power=30, sensitivity=Decimal("2.5")), 9)


class CapabilityCurveZeroPowerPerDoublingTests(TestCase):
    """A legal-but-degenerate power_per_doubling=0 row must degrade to disabled.

    ``PositiveIntegerField`` only rejects negatives, so a row bypassing
    ``full_clean()`` (or written before the validator existed) can still carry a
    0. The helper's guard is the second line of defense against
    ``decimal.DivisionByZero``.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        CapabilityPowerConfig.objects.create(pk=1, power_per_doubling=0)

    def test_zero_power_per_doubling_returns_base(self) -> None:
        self.assertEqual(apply_capability_curve(5, power=50, sensitivity=Decimal("1.0")), 5)


class CapabilityPowerConfigValidationTests(TestCase):
    """full_clean() rejects power_per_doubling=0 before it ever reaches the curve."""

    def test_full_clean_rejects_zero_power_per_doubling(self) -> None:
        config = CapabilityPowerConfig(pk=1, power_per_doubling=0)
        with self.assertRaises(ValidationError):
            config.full_clean()


class CapabilityCurveTests(TestCase):
    """With a config row the curve doubles every power_per_doubling points."""

    @classmethod
    def setUpTestData(cls) -> None:
        CapabilityPowerConfig.objects.create(pk=1, power_per_doubling=10)

    def test_zero_sensitivity_is_identity(self) -> None:
        self.assertEqual(apply_capability_curve(5, power=50, sensitivity=Decimal(0)), 5)

    def test_zero_power_is_identity(self) -> None:
        self.assertEqual(apply_capability_curve(5, power=0, sensitivity=Decimal("1.0")), 5)

    def test_exactly_one_doubling(self) -> None:
        self.assertEqual(apply_capability_curve(5, power=10, sensitivity=Decimal("1.0")), 10)

    def test_two_doublings(self) -> None:
        self.assertEqual(apply_capability_curve(5, power=20, sensitivity=Decimal("1.0")), 20)

    def test_ladder_calibration_reaches_mythic(self) -> None:
        """base 5 at power 50 lands at 160 — the ADR-0164 mythic band."""
        self.assertEqual(apply_capability_curve(5, power=50, sensitivity=Decimal("1.0")), 160)

    def test_sensitivity_scales_the_exponent(self) -> None:
        """sensitivity 2 doubles twice as fast: power 10 -> two doublings."""
        self.assertEqual(apply_capability_curve(5, power=10, sensitivity=Decimal("2.0")), 20)

    def test_fractional_sensitivity(self) -> None:
        """sensitivity 0.1 at power 10 is one tenth of a doubling: 5 * 2**0.1 ~= 5.36 -> 5."""
        self.assertEqual(apply_capability_curve(5, power=10, sensitivity=Decimal("0.1")), 5)

    def test_monotonic_in_power(self) -> None:
        values = [apply_capability_curve(5, power=p, sensitivity=Decimal("1.0")) for p in range(40)]
        self.assertEqual(values, sorted(values))

    def test_never_below_base(self) -> None:
        for power in (0, 1, 7, 33):
            self.assertGreaterEqual(
                apply_capability_curve(5, power=power, sensitivity=Decimal("1.0")), 5
            )

    def test_zero_base_stays_zero(self) -> None:
        self.assertEqual(apply_capability_curve(0, power=50, sensitivity=Decimal("1.0")), 0)

    def test_negative_power_clamps_to_base(self) -> None:
        """A negative aggregate must never shrink a capability below its authored base."""
        self.assertEqual(apply_capability_curve(5, power=-30, sensitivity=Decimal("1.0")), 5)
