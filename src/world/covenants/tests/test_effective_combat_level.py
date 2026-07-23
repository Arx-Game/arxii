"""Tests for effective_combat_level seam + bond adjustment math (#1165).

covenant.level=4, band_width=2 => band [2, 6].
adjacency_offset=1.
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import (
    CharacterClassFactory,
    CharacterClassLevelFactory,
    ClassStageHealthRateFactory,
)
from world.covenants.constants import MentorBondAdjusted
from world.covenants.factories import CovenantFactory, MentorBondFactory, seed_mentor_bond_defaults
from world.covenants.mentorship import (
    _adjusted_level_for_mentor,
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
        character=sheet,
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


class BondLifecycleHealthRecomputeTests(TestCase):
    """establish_mentor_bond and dissolve_mentor_bond recompute health for both parties (#1256)."""

    def setUp(self):
        seed_mentor_bond_defaults()
        self.covenant = CovenantFactory(level=4)  # band [2, 6]
        self.char_class = CharacterClassFactory()
        ClassStageHealthRateFactory(character_class=self.char_class, health_per_level=10)

    def _make_sheet_with_vitals(self, level: int):
        """Create a sheet with a primary class level and vitals (base_max_health=None)."""
        from world.vitals.factories import CharacterVitalsFactory

        sheet = CharacterSheetFactory()
        CharacterClassLevelFactory(
            character=sheet,
            character_class=self.char_class,
            level=level,
            is_primary=True,
        )
        CharacterVitalsFactory(
            character_sheet=sheet, base_max_health=None, health=10, max_health=10
        )
        return sheet

    def test_establishing_bond_recomputes_sidekick_health(self):
        """Forming a sidekick bond raises the sidekick's effective level → more health."""
        from world.covenants.mentorship import establish_mentor_bond
        from world.vitals.models import CharacterVitals

        # mentor raw 4 (in band [2,6]), sidekick raw 1 (out of band) → adjusted_party=SIDEKICK
        mentor_sheet = self._make_sheet_with_vitals(4)
        sidekick_sheet = self._make_sheet_with_vitals(1)

        before = CharacterVitals.objects.get(character_sheet=sidekick_sheet).max_health

        establish_mentor_bond(
            covenant=self.covenant,
            mentor_sheet=mentor_sheet,
            sidekick_sheet=sidekick_sheet,
        )

        after = CharacterVitals.objects.get(character_sheet=sidekick_sheet).max_health
        # sidekick elevated from raw 1 to effective 3 (= 4-1 adjacency), so health grows.
        self.assertGreater(after, before)

    def test_dissolving_bond_recomputes_health(self):
        """Dissolving a bond reverts the sidekick's elevated health back toward the raw level."""
        from world.covenants.mentorship import dissolve_mentor_bond, establish_mentor_bond
        from world.vitals.models import CharacterVitals

        mentor_sheet = self._make_sheet_with_vitals(4)
        sidekick_sheet = self._make_sheet_with_vitals(1)

        bond = establish_mentor_bond(
            covenant=self.covenant,
            mentor_sheet=mentor_sheet,
            sidekick_sheet=sidekick_sheet,
        )
        after_establish = CharacterVitals.objects.get(character_sheet=sidekick_sheet).max_health

        dissolve_mentor_bond(bond)

        after_dissolve = CharacterVitals.objects.get(character_sheet=sidekick_sheet).max_health
        # After dissolve, effective level drops back to raw 1 → health decreases.
        self.assertLess(after_dissolve, after_establish)


class CrossCovenantMentorIsolationTests(TestCase):
    """Mentor bonded as MENTOR in two covenants: each covenant aggregates its own sidekicks (#1264).

    Covenant A: level=10, band [8, 12]. Sidekick S_A primary level=10.
      expected = clamp(10 + 1, 8, 12) = 11
    Covenant B: level=6, band [4, 8]. Sidekick S_B primary level=4.
      expected = clamp(4 + 1, 4, 8) = 5
    The two covenants must yield different results driven by their own sidekick.
    """

    def setUp(self):
        seed_mentor_bond_defaults()
        # Covenant A: level=10, band_width=2 → band [8, 12]
        self.covenant_a = CovenantFactory(level=10)
        # Covenant B: level=6, band_width=2 → band [4, 8]
        self.covenant_b = CovenantFactory(level=6)

    def test_mentor_aggregates_each_covenant_independently(self):
        """Mentor M in covenant A (sidekick level 10) and covenant B (sidekick level 4).

        _adjusted_level_for_mentor must draw only from each covenant's own sidekick bonds.
        Covenant A expected: clamp(10 + 1, 8, 12) = 11.
        Covenant B expected: clamp(4 + 1, 4, 8) = 5.
        """
        mentor_sheet = CharacterSheetFactory()
        sidekick_a = CharacterSheetFactory()
        sidekick_b = CharacterSheetFactory()

        # Mentor is out-of-band in both covenants (level 20 is outside [8,12] and [4,8]).
        _set_primary_level(mentor_sheet, 20)
        # S_A primary level 10 — in-band for covenant A [8, 12], drives A's calculation.
        _set_primary_level(sidekick_a, 10)
        # S_B primary level 4 — in-band for covenant B [4, 8], drives B's calculation.
        _set_primary_level(sidekick_b, 4)

        bond_in_a = MentorBondFactory(
            covenant=self.covenant_a,
            mentor_sheet=mentor_sheet,
            sidekick_sheet=sidekick_a,
            adjusted_party=MentorBondAdjusted.MENTOR,
        )
        bond_in_b = MentorBondFactory(
            covenant=self.covenant_b,
            mentor_sheet=mentor_sheet,
            sidekick_sheet=sidekick_b,
            adjusted_party=MentorBondAdjusted.MENTOR,
        )

        # Covenant A: clamp(10 + 1, 8, 12) = 11
        self.assertEqual(_adjusted_level_for_mentor(bond_in_a), 11)
        # Covenant B: clamp(4 + 1, 4, 8) = 5
        self.assertEqual(_adjusted_level_for_mentor(bond_in_b), 5)
        # Sanity: the two covenants yield different results driven by their own sidekick.
        result_a = _adjusted_level_for_mentor(bond_in_a)
        result_b = _adjusted_level_for_mentor(bond_in_b)
        self.assertGreater(result_a, result_b)
