"""Tests for Mentor's Vow gate + establish/dissolve bond services (#1165).

covenant.level=4, band_width=2 => band [2, 6].

Test scenarios per the brief:
1. Out-of-band join via add_member raises VowGateError.
2. After establish_mentor_bond, the same join succeeds.
3. In-band join is unaffected (no error).
4. establish_mentor_bond raises MentorBondError when partner is also out-of-band.
5. max_sidekicks_per_mentor cap: a second sidekick is rejected.
"""

from django.test import TestCase
from django.utils import timezone

from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory
from world.covenants.exceptions import MentorBondError, VowGateError
from world.covenants.factories import (
    CovenantFactory,
    CovenantRoleFactory,
    seed_mentor_bond_defaults,
)
from world.covenants.mentorship import dissolve_mentor_bond, establish_mentor_bond
from world.covenants.services import add_member


def _set_primary_level(sheet, level: int) -> None:
    """Helper: give sheet.character a primary CharacterClassLevel at the given level."""
    char_class = CharacterClassFactory()
    CharacterClassLevelFactory(
        character=sheet,
        character_class=char_class,
        level=level,
        is_primary=True,
    )


class VowGateAddMemberTests(TestCase):
    """Tests for the VowGate wired into add_member."""

    def setUp(self):
        seed_mentor_bond_defaults()
        self.covenant = CovenantFactory(level=4)  # band [2, 6]
        self.role = CovenantRoleFactory(covenant_type=self.covenant.covenant_type)

    def test_out_of_band_join_raises_vow_gate_error(self):
        """A character with raw level 1 (below band [2,6]) cannot join without a bond."""
        sheet = CharacterSheetFactory()
        _set_primary_level(sheet, 1)  # out of band

        with self.assertRaises(VowGateError):
            add_member(covenant=self.covenant, character_sheet=sheet, role=self.role)

    def test_in_band_join_succeeds(self):
        """A character with raw level 4 (in band [2,6]) can join freely."""
        sheet = CharacterSheetFactory()
        _set_primary_level(sheet, 4)  # in band

        # Should not raise
        row = add_member(covenant=self.covenant, character_sheet=sheet, role=self.role)
        self.assertIsNotNone(row.pk)

    def test_out_of_band_above_join_raises_vow_gate_error(self):
        """A character with raw level 8 (above band [2,6]) cannot join without a bond."""
        sheet = CharacterSheetFactory()
        _set_primary_level(sheet, 8)  # above band

        with self.assertRaises(VowGateError):
            add_member(covenant=self.covenant, character_sheet=sheet, role=self.role)

    def test_out_of_band_join_allowed_after_bond_as_sidekick(self):
        """After establish_mentor_bond, the out-of-band sidekick may join."""
        mentor_sheet = CharacterSheetFactory()
        sidekick_sheet = CharacterSheetFactory()
        _set_primary_level(mentor_sheet, 4)  # in band
        _set_primary_level(sidekick_sheet, 1)  # out of band (sidekick)

        establish_mentor_bond(
            covenant=self.covenant,
            mentor_sheet=mentor_sheet,
            sidekick_sheet=sidekick_sheet,
        )

        # Now sidekick (out-of-band) should be allowed to join
        row = add_member(covenant=self.covenant, character_sheet=sidekick_sheet, role=self.role)
        self.assertIsNotNone(row.pk)

    def test_out_of_band_join_allowed_after_bond_as_mentor(self):
        """After establish_mentor_bond, the out-of-band mentor may join."""
        mentor_sheet = CharacterSheetFactory()
        sidekick_sheet = CharacterSheetFactory()
        _set_primary_level(mentor_sheet, 8)  # out of band (mentor)
        _set_primary_level(sidekick_sheet, 4)  # in band

        establish_mentor_bond(
            covenant=self.covenant,
            mentor_sheet=mentor_sheet,
            sidekick_sheet=sidekick_sheet,
        )

        # Now mentor (out-of-band) should be allowed to join
        row = add_member(covenant=self.covenant, character_sheet=mentor_sheet, role=self.role)
        self.assertIsNotNone(row.pk)

    def test_vow_gate_error_has_user_message(self):
        """VowGateError carries a user_message attribute."""
        sheet = CharacterSheetFactory()
        _set_primary_level(sheet, 1)

        with self.assertRaises(VowGateError) as cm:
            add_member(covenant=self.covenant, character_sheet=sheet, role=self.role)

        self.assertTrue(hasattr(cm.exception, "user_message"))
        self.assertIsInstance(cm.exception.user_message, str)
        self.assertGreater(len(cm.exception.user_message), 0)


class EstablishMentorBondTests(TestCase):
    """Tests for establish_mentor_bond service."""

    def setUp(self):
        seed_mentor_bond_defaults()
        self.covenant = CovenantFactory(level=4)  # band [2, 6]

    def test_establish_bond_creates_row(self):
        """establish_mentor_bond creates a MentorBond with the right adjusted_party."""
        from world.covenants.constants import MentorBondAdjusted

        mentor_sheet = CharacterSheetFactory()
        sidekick_sheet = CharacterSheetFactory()
        _set_primary_level(mentor_sheet, 4)  # in band
        _set_primary_level(sidekick_sheet, 1)  # out of band => sidekick is adjusted

        bond = establish_mentor_bond(
            covenant=self.covenant,
            mentor_sheet=mentor_sheet,
            sidekick_sheet=sidekick_sheet,
        )

        self.assertIsNotNone(bond.pk)
        self.assertEqual(bond.covenant, self.covenant)
        self.assertEqual(bond.mentor_sheet, mentor_sheet)
        self.assertEqual(bond.sidekick_sheet, sidekick_sheet)
        self.assertEqual(bond.adjusted_party, MentorBondAdjusted.SIDEKICK)
        self.assertIsNone(bond.dissolved_at)

    def test_establish_bond_mentor_adjusted_when_mentor_is_out_of_band(self):
        """When mentor is out-of-band and sidekick is in-band, adjusted_party=MENTOR."""
        from world.covenants.constants import MentorBondAdjusted

        mentor_sheet = CharacterSheetFactory()
        sidekick_sheet = CharacterSheetFactory()
        _set_primary_level(mentor_sheet, 8)  # out of band => mentor is adjusted
        _set_primary_level(sidekick_sheet, 4)  # in band

        bond = establish_mentor_bond(
            covenant=self.covenant,
            mentor_sheet=mentor_sheet,
            sidekick_sheet=sidekick_sheet,
        )

        self.assertEqual(bond.adjusted_party, MentorBondAdjusted.MENTOR)

    def test_establish_bond_raises_when_both_in_band(self):
        """MentorBondError when both mentor and sidekick are in band (no outlier)."""
        mentor_sheet = CharacterSheetFactory()
        sidekick_sheet = CharacterSheetFactory()
        _set_primary_level(mentor_sheet, 3)  # in band
        _set_primary_level(sidekick_sheet, 5)  # in band

        with self.assertRaises(MentorBondError):
            establish_mentor_bond(
                covenant=self.covenant,
                mentor_sheet=mentor_sheet,
                sidekick_sheet=sidekick_sheet,
            )

    def test_establish_bond_raises_when_both_out_of_band(self):
        """MentorBondError when both mentor and sidekick are out of band."""
        mentor_sheet = CharacterSheetFactory()
        sidekick_sheet = CharacterSheetFactory()
        _set_primary_level(mentor_sheet, 8)  # out of band
        _set_primary_level(sidekick_sheet, 1)  # out of band

        with self.assertRaises(MentorBondError):
            establish_mentor_bond(
                covenant=self.covenant,
                mentor_sheet=mentor_sheet,
                sidekick_sheet=sidekick_sheet,
            )

    def test_establish_bond_raises_when_partner_not_in_band(self):
        """MentorBondError: the out-of-band party is correctly identified,
        but the partner must be in band. (Same as both-out-of-band scenario.)"""
        mentor_sheet = CharacterSheetFactory()
        sidekick_sheet = CharacterSheetFactory()
        _set_primary_level(mentor_sheet, 9)  # out of band
        _set_primary_level(sidekick_sheet, 1)  # also out of band

        with self.assertRaises(MentorBondError):
            establish_mentor_bond(
                covenant=self.covenant,
                mentor_sheet=mentor_sheet,
                sidekick_sheet=sidekick_sheet,
            )

    def test_cap_enforced_when_max_sidekicks_set(self):
        """When max_sidekicks_per_mentor=1, a second sidekick is rejected."""
        from world.covenants.models import MentorBondConfig

        cfg = MentorBondConfig.objects.get(pk=1)
        cfg.max_sidekicks_per_mentor = 1
        cfg.save()

        mentor_sheet = CharacterSheetFactory()
        sidekick_a = CharacterSheetFactory()
        sidekick_b = CharacterSheetFactory()
        _set_primary_level(mentor_sheet, 4)  # in band
        _set_primary_level(sidekick_a, 1)  # out of band
        _set_primary_level(sidekick_b, 1)  # out of band

        # First bond succeeds
        establish_mentor_bond(
            covenant=self.covenant,
            mentor_sheet=mentor_sheet,
            sidekick_sheet=sidekick_a,
        )

        # Second bond is rejected due to cap
        with self.assertRaises(MentorBondError):
            establish_mentor_bond(
                covenant=self.covenant,
                mentor_sheet=mentor_sheet,
                sidekick_sheet=sidekick_b,
            )

    def test_cap_not_enforced_when_max_sidekicks_none(self):
        """When max_sidekicks_per_mentor=None, multiple sidekicks are allowed."""
        from world.covenants.models import MentorBondConfig

        cfg = MentorBondConfig.objects.get(pk=1)
        self.assertIsNone(cfg.max_sidekicks_per_mentor)

        mentor_sheet = CharacterSheetFactory()
        sidekick_a = CharacterSheetFactory()
        sidekick_b = CharacterSheetFactory()
        _set_primary_level(mentor_sheet, 4)  # in band
        _set_primary_level(sidekick_a, 1)  # out of band
        _set_primary_level(sidekick_b, 1)  # out of band

        # Both bonds should succeed
        bond_a = establish_mentor_bond(
            covenant=self.covenant,
            mentor_sheet=mentor_sheet,
            sidekick_sheet=sidekick_a,
        )
        bond_b = establish_mentor_bond(
            covenant=self.covenant,
            mentor_sheet=mentor_sheet,
            sidekick_sheet=sidekick_b,
        )
        self.assertIsNotNone(bond_a.pk)
        self.assertIsNotNone(bond_b.pk)

    def test_mentor_bond_error_has_user_message(self):
        """MentorBondError carries a user_message attribute."""
        mentor_sheet = CharacterSheetFactory()
        sidekick_sheet = CharacterSheetFactory()
        _set_primary_level(mentor_sheet, 4)  # in band
        _set_primary_level(sidekick_sheet, 4)  # also in band => error

        with self.assertRaises(MentorBondError) as cm:
            establish_mentor_bond(
                covenant=self.covenant,
                mentor_sheet=mentor_sheet,
                sidekick_sheet=sidekick_sheet,
            )

        self.assertTrue(hasattr(cm.exception, "user_message"))


class DissolveMentorBondTests(TestCase):
    """Tests for dissolve_mentor_bond service."""

    def setUp(self):
        seed_mentor_bond_defaults()
        self.covenant = CovenantFactory(level=4)

    def test_dissolve_sets_dissolved_at(self):
        """dissolve_mentor_bond sets dissolved_at on the bond."""
        mentor_sheet = CharacterSheetFactory()
        sidekick_sheet = CharacterSheetFactory()
        _set_primary_level(mentor_sheet, 4)
        _set_primary_level(sidekick_sheet, 1)

        bond = establish_mentor_bond(
            covenant=self.covenant,
            mentor_sheet=mentor_sheet,
            sidekick_sheet=sidekick_sheet,
        )
        self.assertIsNone(bond.dissolved_at)

        dissolve_mentor_bond(bond)

        bond.refresh_from_db()
        self.assertIsNotNone(bond.dissolved_at)

    def test_dissolve_bond_before_now(self):
        """dissolved_at is set to approximately now."""
        from datetime import timedelta

        mentor_sheet = CharacterSheetFactory()
        sidekick_sheet = CharacterSheetFactory()
        _set_primary_level(mentor_sheet, 4)
        _set_primary_level(sidekick_sheet, 1)

        bond = establish_mentor_bond(
            covenant=self.covenant,
            mentor_sheet=mentor_sheet,
            sidekick_sheet=sidekick_sheet,
        )
        before = timezone.now()
        dissolve_mentor_bond(bond)
        after = timezone.now()

        bond.refresh_from_db()
        self.assertGreaterEqual(bond.dissolved_at, before - timedelta(seconds=1))
        self.assertLessEqual(bond.dissolved_at, after + timedelta(seconds=1))

    def test_dissolved_bond_no_longer_allows_join(self):
        """After dissolve, the formerly-bonded out-of-band character can no longer join."""
        mentor_sheet = CharacterSheetFactory()
        sidekick_sheet = CharacterSheetFactory()
        _set_primary_level(mentor_sheet, 4)
        _set_primary_level(sidekick_sheet, 1)

        role = CovenantRoleFactory(covenant_type=self.covenant.covenant_type)

        bond = establish_mentor_bond(
            covenant=self.covenant,
            mentor_sheet=mentor_sheet,
            sidekick_sheet=sidekick_sheet,
        )
        dissolve_mentor_bond(bond)

        with self.assertRaises(VowGateError):
            add_member(covenant=self.covenant, character_sheet=sidekick_sheet, role=role)
