"""Tests for effective_combat_level seam + bond adjustment math (#1165).

covenant.level=4, band_width=2 => band [2, 6].
adjacency_offset=1.
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory
from world.covenants.constants import MentorBondAdjusted
from world.covenants.factories import CovenantFactory, MentorBondFactory, seed_mentor_bond_defaults
from world.covenants.mentorship import (
    active_bond_adjusting,
    bond_adjusted_level,
    covenant_band,
    effective_combat_level,
    is_bond_graduated,
    is_in_band,
)


def _set_primary_level(sheet, level: int) -> None:
    """Helper: give sheet.character a primary CharacterClassLevel at the given level."""
    char_class = CharacterClassFactory()
    CharacterClassLevelFactory(
        character=sheet.character,
        character_class=char_class,
        level=level,
        is_primary=True,
    )


class CovenantBandTests(TestCase):
    def setUp(self):
        seed_mentor_bond_defaults()
        self.covenant = CovenantFactory(level=4)

    def test_band_returns_correct_tuple(self):
        lo, hi = covenant_band(self.covenant)
        self.assertEqual(lo, 2)
        self.assertEqual(hi, 6)

    def test_is_in_band_true_at_lower_bound(self):
        self.assertTrue(is_in_band(self.covenant, 2))

    def test_is_in_band_true_at_upper_bound(self):
        self.assertTrue(is_in_band(self.covenant, 6))

    def test_is_in_band_false_below(self):
        self.assertFalse(is_in_band(self.covenant, 1))

    def test_is_in_band_false_above(self):
        self.assertFalse(is_in_band(self.covenant, 7))

    def test_is_in_band_true_in_middle(self):
        self.assertTrue(is_in_band(self.covenant, 4))


class SidekickAdjustmentTests(TestCase):
    """Tests for SIDEKICK adjusted_party bond math."""

    def setUp(self):
        seed_mentor_bond_defaults()
        self.covenant = CovenantFactory(level=4)  # band [2, 6]

    def test_sidekick_raised_to_mentor_minus_offset(self):
        """mentor raw 5, sidekick raw 1 => effective sidekick = clamp(5-1, [2,6]) = 4."""
        mentor_sheet = CharacterSheetFactory()
        sidekick_sheet = CharacterSheetFactory()
        _set_primary_level(mentor_sheet, 5)
        _set_primary_level(sidekick_sheet, 1)

        MentorBondFactory(
            covenant=self.covenant,
            mentor_sheet=mentor_sheet,
            sidekick_sheet=sidekick_sheet,
            adjusted_party=MentorBondAdjusted.SIDEKICK,
        )

        self.assertEqual(effective_combat_level(sidekick_sheet), 4)

    def test_clamped_to_band_top(self):
        """mentor raw 9 (still > band), sidekick adjusted: clamp(9-1, [2,6]) = 6."""
        mentor_sheet = CharacterSheetFactory()
        sidekick_sheet = CharacterSheetFactory()
        _set_primary_level(mentor_sheet, 9)
        _set_primary_level(sidekick_sheet, 1)

        MentorBondFactory(
            covenant=self.covenant,
            mentor_sheet=mentor_sheet,
            sidekick_sheet=sidekick_sheet,
            adjusted_party=MentorBondAdjusted.SIDEKICK,
        )

        self.assertEqual(effective_combat_level(sidekick_sheet), 6)

    def test_clamped_to_band_bottom(self):
        """mentor raw 2 (low), sidekick raw 1: clamp(2-1, [2,6]) = clamp(1, [2,6]) = 2."""
        mentor_sheet = CharacterSheetFactory()
        sidekick_sheet = CharacterSheetFactory()
        _set_primary_level(mentor_sheet, 2)
        _set_primary_level(sidekick_sheet, 1)

        MentorBondFactory(
            covenant=self.covenant,
            mentor_sheet=mentor_sheet,
            sidekick_sheet=sidekick_sheet,
            adjusted_party=MentorBondAdjusted.SIDEKICK,
        )

        # clamp(2-1=1, [2,6]) = 2
        self.assertEqual(effective_combat_level(sidekick_sheet), 2)

    def test_graduated_bond_returns_raw(self):
        """sidekick leveled to 3 (in band) => effective = raw 3, bond ignored."""
        mentor_sheet = CharacterSheetFactory()
        sidekick_sheet = CharacterSheetFactory()
        _set_primary_level(mentor_sheet, 8)
        _set_primary_level(sidekick_sheet, 3)  # 3 is in [2, 6]

        bond = MentorBondFactory(
            covenant=self.covenant,
            mentor_sheet=mentor_sheet,
            sidekick_sheet=sidekick_sheet,
            adjusted_party=MentorBondAdjusted.SIDEKICK,
        )

        self.assertTrue(is_bond_graduated(bond))
        self.assertEqual(effective_combat_level(sidekick_sheet), 3)

    def test_graduated_bond_not_adjusting(self):
        """active_bond_adjusting returns None for graduated bonds."""
        mentor_sheet = CharacterSheetFactory()
        sidekick_sheet = CharacterSheetFactory()
        _set_primary_level(mentor_sheet, 8)
        _set_primary_level(sidekick_sheet, 4)  # 4 is in [2, 6]

        MentorBondFactory(
            covenant=self.covenant,
            mentor_sheet=mentor_sheet,
            sidekick_sheet=sidekick_sheet,
            adjusted_party=MentorBondAdjusted.SIDEKICK,
        )

        self.assertIsNone(active_bond_adjusting(sidekick_sheet))


class MentorAdjustmentTests(TestCase):
    """Tests for MENTOR adjusted_party bond math."""

    def setUp(self):
        seed_mentor_bond_defaults()
        self.covenant = CovenantFactory(level=4)  # band [2, 6]

    def test_mentor_suppressed_to_highest_sidekick_plus_offset(self):
        """mentor raw 10 mentoring sidekicks raw 3 and 4 => clamp(4+1, [2,6]) = 5."""
        mentor_sheet = CharacterSheetFactory()
        sidekick_a = CharacterSheetFactory()
        sidekick_b = CharacterSheetFactory()
        _set_primary_level(mentor_sheet, 10)
        _set_primary_level(sidekick_a, 3)
        _set_primary_level(sidekick_b, 4)

        MentorBondFactory(
            covenant=self.covenant,
            mentor_sheet=mentor_sheet,
            sidekick_sheet=sidekick_a,
            adjusted_party=MentorBondAdjusted.MENTOR,
        )
        MentorBondFactory(
            covenant=self.covenant,
            mentor_sheet=mentor_sheet,
            sidekick_sheet=sidekick_b,
            adjusted_party=MentorBondAdjusted.MENTOR,
        )

        self.assertEqual(effective_combat_level(mentor_sheet), 5)

    def test_mentor_clamp_to_band_top(self):
        """top sidekick raw 9 => clamp(9+1=10, [2,6]) = 6."""
        mentor_sheet = CharacterSheetFactory()
        sidekick_sheet = CharacterSheetFactory()
        _set_primary_level(mentor_sheet, 15)
        _set_primary_level(sidekick_sheet, 9)

        MentorBondFactory(
            covenant=self.covenant,
            mentor_sheet=mentor_sheet,
            sidekick_sheet=sidekick_sheet,
            adjusted_party=MentorBondAdjusted.MENTOR,
        )

        self.assertEqual(effective_combat_level(mentor_sheet), 6)

    def test_mentor_graduated_returns_raw(self):
        """mentor raw 4 (in band [2,6]) => graduated => returns raw 4."""
        mentor_sheet = CharacterSheetFactory()
        sidekick_sheet = CharacterSheetFactory()
        _set_primary_level(mentor_sheet, 4)
        _set_primary_level(sidekick_sheet, 1)

        bond = MentorBondFactory(
            covenant=self.covenant,
            mentor_sheet=mentor_sheet,
            sidekick_sheet=sidekick_sheet,
            adjusted_party=MentorBondAdjusted.MENTOR,
        )

        self.assertTrue(is_bond_graduated(bond))
        self.assertEqual(effective_combat_level(mentor_sheet), 4)


class NoBondTests(TestCase):
    """Tests for characters with no active bond."""

    def setUp(self):
        seed_mentor_bond_defaults()

    def test_no_bond_returns_raw_primary(self):
        """effective = get_character_path_level when no active bond."""
        sheet = CharacterSheetFactory()
        _set_primary_level(sheet, 7)

        self.assertEqual(effective_combat_level(sheet), 7)

    def test_no_bond_no_class_level_returns_1(self):
        """effective falls back to 1 when no CharacterClassLevel rows."""
        sheet = CharacterSheetFactory()

        self.assertEqual(effective_combat_level(sheet), 1)

    def test_active_bond_adjusting_none_when_no_bond(self):
        sheet = CharacterSheetFactory()
        _set_primary_level(sheet, 5)

        self.assertIsNone(active_bond_adjusting(sheet))

    def test_bond_adjusted_level_none_when_no_bond(self):
        sheet = CharacterSheetFactory()
        _set_primary_level(sheet, 5)

        self.assertIsNone(bond_adjusted_level(sheet))


class DissolvedBondTests(TestCase):
    """Dissolved bonds must not be counted as active."""

    def setUp(self):
        seed_mentor_bond_defaults()
        self.covenant = CovenantFactory(level=4)

    def test_dissolved_bond_ignored(self):
        """A dissolved bond does not adjust the sidekick's level."""
        from django.utils import timezone

        mentor_sheet = CharacterSheetFactory()
        sidekick_sheet = CharacterSheetFactory()
        _set_primary_level(mentor_sheet, 8)
        _set_primary_level(sidekick_sheet, 1)

        bond = MentorBondFactory(
            covenant=self.covenant,
            mentor_sheet=mentor_sheet,
            sidekick_sheet=sidekick_sheet,
            adjusted_party=MentorBondAdjusted.SIDEKICK,
        )
        bond.dissolved_at = timezone.now()
        bond.save()

        # Should fall back to raw (1)
        self.assertEqual(effective_combat_level(sidekick_sheet), 1)
        self.assertIsNone(active_bond_adjusting(sidekick_sheet))
