"""Tests for DamageSuccessLevelMultiplier lookup."""

from decimal import Decimal

from evennia.utils.test_resources import EvenniaTestCase


class GetDamageMultiplierTests(EvenniaTestCase):
    def test_returns_zero_when_table_empty(self):
        from world.conditions.services import get_damage_multiplier

        self.assertEqual(get_damage_multiplier(2), Decimal(0))

    def test_returns_full_at_threshold(self):
        from world.conditions.factories import DamageSuccessLevelMultiplierFactory
        from world.conditions.services import get_damage_multiplier

        DamageSuccessLevelMultiplierFactory(min_success_level=2, multiplier=Decimal("1.00"))
        DamageSuccessLevelMultiplierFactory(min_success_level=1, multiplier=Decimal("0.50"))
        self.assertEqual(get_damage_multiplier(2), Decimal("1.00"))

    def test_returns_partial_below_full(self):
        from world.conditions.factories import DamageSuccessLevelMultiplierFactory
        from world.conditions.services import get_damage_multiplier

        DamageSuccessLevelMultiplierFactory(min_success_level=2, multiplier=Decimal("1.00"))
        DamageSuccessLevelMultiplierFactory(min_success_level=1, multiplier=Decimal("0.50"))
        self.assertEqual(get_damage_multiplier(1), Decimal("0.50"))

    def test_returns_zero_below_lowest(self):
        from world.conditions.factories import DamageSuccessLevelMultiplierFactory
        from world.conditions.services import get_damage_multiplier

        DamageSuccessLevelMultiplierFactory(min_success_level=1, multiplier=Decimal("0.50"))
        self.assertEqual(get_damage_multiplier(0), Decimal(0))

    def test_highest_threshold_wins(self):
        from world.conditions.factories import DamageSuccessLevelMultiplierFactory
        from world.conditions.services import get_damage_multiplier

        DamageSuccessLevelMultiplierFactory(min_success_level=1, multiplier=Decimal("0.50"))
        DamageSuccessLevelMultiplierFactory(min_success_level=2, multiplier=Decimal("1.00"))
        DamageSuccessLevelMultiplierFactory(min_success_level=3, multiplier=Decimal("1.50"))
        self.assertEqual(get_damage_multiplier(3), Decimal("1.50"))
