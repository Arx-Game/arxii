"""DoT round-tick damage respects damage-type resistance via the unified seam (#1588)."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from world.conditions.services import resolve_damage_type_resistance


class DotRespectsResistanceTest(TestCase):
    """The vitals _apply_round_tick_damage seam now nets resistance (#1588).

    These tests assert the wiring at the unit level: the unified seam is what the
    DoT path calls. The full E2E (sunlight DoT through the peril pipeline) lives in
    the scenes sunlight-exposure E2E.
    """

    def test_resolve_seam_reduces_dot_damage_by_resistance(self):
        """A character with fire resistance takes less fire DoT damage."""
        char = MagicMock()
        char.conditions.resistance_modifier.return_value = 3
        with patch(
            "world.magic.services.gift_thread_resistance",
            return_value=0,
        ):
            # 5 fire damage - 3 condition resistance = 2
            self.assertEqual(resolve_damage_type_resistance(char, 5, MagicMock(pk=1)), 2)

    def test_resolve_seam_zeroes_dot_when_resistance_exceeds(self):
        """High resistance zeroes the DoT (immunity-as-resistance)."""
        char = MagicMock()
        char.conditions.resistance_modifier.return_value = 100
        with patch(
            "world.magic.services.gift_thread_resistance",
            return_value=0,
        ):
            self.assertEqual(resolve_damage_type_resistance(char, 5, MagicMock(pk=1)), 0)

    def test_resolve_seam_increases_dot_for_vulnerability(self):
        """A fire vulnerability increases fire DoT damage above the base."""
        char = MagicMock()
        char.conditions.resistance_modifier.return_value = -4
        with patch(
            "world.magic.services.gift_thread_resistance",
            return_value=0,
        ):
            # 5 fire + 4 vulnerability = 9
            self.assertEqual(resolve_damage_type_resistance(char, 5, MagicMock(pk=1)), 9)
