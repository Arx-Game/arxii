"""Tests for PenetrationOutcomeFactor lookup (#639)."""

from decimal import Decimal

from evennia.utils.test_resources import EvenniaTestCase


class GetPenetrationFactorTests(EvenniaTestCase):
    def test_returns_full_when_table_empty(self):
        """Unauthored ladder → full power (never accidentally zero)."""
        from world.conditions.services import get_penetration_factor

        self.assertEqual(get_penetration_factor(2), Decimal("1.00"))

    def test_returns_full_at_threshold(self):
        from world.conditions.factories import wire_penetration_factors
        from world.conditions.services import get_penetration_factor

        wire_penetration_factors()
        self.assertEqual(get_penetration_factor(1), Decimal("1.00"))

    def test_returns_partial(self):
        from world.conditions.factories import wire_penetration_factors
        from world.conditions.services import get_penetration_factor

        wire_penetration_factors()
        self.assertEqual(get_penetration_factor(0), Decimal("0.50"))

    def test_returns_bounce_below_lowest(self):
        from world.conditions.factories import wire_penetration_factors
        from world.conditions.services import get_penetration_factor

        wire_penetration_factors()
        self.assertEqual(get_penetration_factor(-1), Decimal("0.00"))
        self.assertEqual(get_penetration_factor(-5), Decimal("0.00"))

    def test_highest_threshold_wins(self):
        from world.conditions.factories import wire_penetration_factors
        from world.conditions.services import get_penetration_factor

        wire_penetration_factors()
        self.assertEqual(get_penetration_factor(3), Decimal("1.50"))
        self.assertEqual(get_penetration_factor(5), Decimal("1.50"))
