"""Tests for ClashConfig power-formula knobs (#858).

Verifies that:
- The six old delta_* IntegerFields are gone.
- The seven new DecimalFields exist with correct defaults.
- quality_multiplier_for() returns the correct multiplier per success-level band.
"""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from world.combat.factories import ClashConfigFactory
from world.combat.models import ClashConfig


class ClashConfigPowerFormulaFieldsTests(TestCase):
    """New power-formula fields exist with correct defaults; old delta_* are gone."""

    def setUp(self) -> None:
        self.cfg = ClashConfigFactory()

    def test_power_scale_default(self) -> None:
        self.assertEqual(self.cfg.power_scale, Decimal("0.5"))

    def test_quality_multiplier_critical_default(self) -> None:
        self.assertEqual(self.cfg.quality_multiplier_critical, Decimal("1.5"))

    def test_quality_multiplier_great_default(self) -> None:
        self.assertEqual(self.cfg.quality_multiplier_great, Decimal("1.25"))

    def test_quality_multiplier_success_default(self) -> None:
        self.assertEqual(self.cfg.quality_multiplier_success, Decimal("1.0"))

    def test_quality_multiplier_partial_default(self) -> None:
        self.assertEqual(self.cfg.quality_multiplier_partial, Decimal("0.5"))

    def test_quality_multiplier_failure_default(self) -> None:
        self.assertEqual(self.cfg.quality_multiplier_failure, Decimal("0.0"))

    def test_botch_backfire_fraction_default(self) -> None:
        self.assertEqual(self.cfg.botch_backfire_fraction, Decimal("0.5"))

    def test_delta_critical_success_gone(self) -> None:
        self.assertFalse(hasattr(self.cfg, "delta_critical_success"))

    def test_delta_great_success_gone(self) -> None:
        self.assertFalse(hasattr(self.cfg, "delta_great_success"))

    def test_delta_success_gone(self) -> None:
        self.assertFalse(hasattr(self.cfg, "delta_success"))

    def test_delta_partial_gone(self) -> None:
        self.assertFalse(hasattr(self.cfg, "delta_partial"))

    def test_delta_failure_gone(self) -> None:
        self.assertFalse(hasattr(self.cfg, "delta_failure"))

    def test_delta_botch_gone(self) -> None:
        self.assertFalse(hasattr(self.cfg, "delta_botch"))


class ClashConfigQualityMultiplierForTests(TestCase):
    """quality_multiplier_for() returns the correct banded multiplier."""

    def setUp(self) -> None:
        self.cfg = ClashConfigFactory()

    def test_critical_at_three(self) -> None:
        self.assertEqual(self.cfg.quality_multiplier_for(3), Decimal("1.5"))

    def test_critical_above_three(self) -> None:
        self.assertEqual(self.cfg.quality_multiplier_for(4), Decimal("1.5"))

    def test_great_at_two(self) -> None:
        self.assertEqual(self.cfg.quality_multiplier_for(2), Decimal("1.25"))

    def test_success_at_one(self) -> None:
        self.assertEqual(self.cfg.quality_multiplier_for(1), Decimal("1.0"))

    def test_partial_at_zero(self) -> None:
        self.assertEqual(self.cfg.quality_multiplier_for(0), Decimal("0.5"))

    def test_failure_at_minus_one(self) -> None:
        self.assertEqual(self.cfg.quality_multiplier_for(-1), Decimal("0.0"))

    def test_failure_below_minus_one(self) -> None:
        # Botch handling is the caller's responsibility; success_level <= -1 → failure multiplier.
        self.assertEqual(self.cfg.quality_multiplier_for(-2), Decimal("0.0"))

    def test_field_definition_power_scale(self) -> None:
        field = ClashConfig._meta.get_field("power_scale")
        self.assertEqual(field.default, Decimal("0.5"))
        self.assertEqual(field.max_digits, 5)
        self.assertEqual(field.decimal_places, 2)
        self.assertFalse(field.null)

    def test_field_definition_botch_backfire_fraction(self) -> None:
        field = ClashConfig._meta.get_field("botch_backfire_fraction")
        self.assertEqual(field.default, Decimal("0.5"))
        self.assertEqual(field.max_digits, 5)
        self.assertEqual(field.decimal_places, 2)
        self.assertFalse(field.null)
