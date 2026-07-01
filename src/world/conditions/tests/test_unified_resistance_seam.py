from unittest.mock import MagicMock, patch

from django.test import TestCase

from world.conditions.services import resolve_damage_type_resistance


class ResolveDamageTypeResistanceTest(TestCase):
    def test_none_damage_type_returns_amount_unchanged(self):
        char = MagicMock()
        self.assertEqual(resolve_damage_type_resistance(char, 50, None), 50)

    def test_nets_condition_and_gift_resistance(self):
        char = MagicMock()
        char.conditions.resistance_modifier.return_value = 10
        with patch(
            "world.magic.services.gift_thread_resistance",
            return_value=0,
        ):
            amount = resolve_damage_type_resistance(char, 50, MagicMock(pk=1))
        # 50 - 10 (condition) - 0 (gift) = 40
        self.assertEqual(amount, 40)

    def test_resistance_exceeding_damage_clamps_to_zero(self):
        char = MagicMock()
        char.conditions.resistance_modifier.return_value = 100
        with patch(
            "world.magic.services.gift_thread_resistance",
            return_value=50,
        ):
            amount = resolve_damage_type_resistance(char, 30, MagicMock(pk=1))
        self.assertEqual(amount, 0)

    def test_vulnerability_increases_damage(self):
        """A negative resistance (vulnerability) increases damage above the base."""
        char = MagicMock()
        char.conditions.resistance_modifier.return_value = -20
        with patch(
            "world.magic.services.gift_thread_resistance",
            return_value=0,
        ):
            amount = resolve_damage_type_resistance(char, 30, MagicMock(pk=1))
        self.assertEqual(amount, 50)
