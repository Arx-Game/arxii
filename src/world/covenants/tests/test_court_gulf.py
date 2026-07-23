"""Tests for Court power-tier gulf enforcement at join (#1589 Task 4).

Tier map (TIER_ONE_MAX_LEVEL = 5):
  Level 1-5  → tier 1
  Level 6-10 → tier 2
  Level 11-15 → tier 3
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory
from world.covenants.constants import CovenantType
from world.covenants.exceptions import CourtGulfViolationError
from world.covenants.mentorship import assert_membership_level_allowed
from world.covenants.power_tier import power_tier_for_level


def _set_primary_level(sheet, level: int) -> None:
    """Give sheet.character a primary CharacterClassLevel at the given level."""
    char_class = CharacterClassFactory()
    CharacterClassLevelFactory(
        character=sheet,
        character_class=char_class,
        level=level,
        is_primary=True,
    )


def _make_court_covenant(leader_sheet):
    """Create a COURT Covenant row directly (bypassing create_covenant service)."""
    from world.covenants.factories import CovenantFactory

    return CovenantFactory(covenant_type=CovenantType.COURT, leader=leader_sheet)


class PowerTierForLevelTests(TestCase):
    """Unit tests for power_tier_for_level helper."""

    def test_level_zero_is_tier_one(self):
        self.assertEqual(power_tier_for_level(0), 1)

    def test_level_one_is_tier_one(self):
        self.assertEqual(power_tier_for_level(1), 1)

    def test_level_five_is_tier_one(self):
        self.assertEqual(power_tier_for_level(5), 1)

    def test_level_six_is_tier_two(self):
        self.assertEqual(power_tier_for_level(6), 2)

    def test_level_ten_is_tier_two(self):
        self.assertEqual(power_tier_for_level(10), 2)

    def test_level_eleven_is_tier_three(self):
        self.assertEqual(power_tier_for_level(11), 3)


class CourtGulfEnforcedTests(TestCase):
    """Tests for the >=1 tier gulf rule in assert_membership_level_allowed."""

    def test_same_tier_raises_court_gulf_violation(self):
        """Servant level 6 (tier 2) vs leader level 7 (tier 2) → CourtGulfViolationError."""
        leader = CharacterSheetFactory()
        servant = CharacterSheetFactory()
        _set_primary_level(leader, 7)  # tier 2
        _set_primary_level(servant, 6)  # tier 2 — same tier

        covenant = _make_court_covenant(leader_sheet=leader)

        with self.assertRaises(CourtGulfViolationError):
            assert_membership_level_allowed(covenant=covenant, character_sheet=servant)

    def test_servant_one_tier_below_is_allowed(self):
        """Servant level 5 (tier 1) vs leader level 6 (tier 2) → allowed (no raise)."""
        leader = CharacterSheetFactory()
        servant = CharacterSheetFactory()
        _set_primary_level(leader, 6)  # tier 2
        _set_primary_level(servant, 5)  # tier 1 — one tier below

        covenant = _make_court_covenant(leader_sheet=leader)

        # Must not raise
        assert_membership_level_allowed(covenant=covenant, character_sheet=servant)

    def test_boundary_level5_vs_level10_allowed(self):
        """Level 5 (tier 1) vs level 10 (tier 2) → allowed."""
        leader = CharacterSheetFactory()
        servant = CharacterSheetFactory()
        _set_primary_level(leader, 10)  # tier 2
        _set_primary_level(servant, 5)  # tier 1

        covenant = _make_court_covenant(leader_sheet=leader)

        assert_membership_level_allowed(covenant=covenant, character_sheet=servant)

    def test_boundary_level6_vs_level7_rejected(self):
        """Level 6 (tier 2) vs level 7 (tier 2) → CourtGulfViolationError."""
        leader = CharacterSheetFactory()
        servant = CharacterSheetFactory()
        _set_primary_level(leader, 7)  # tier 2
        _set_primary_level(servant, 6)  # tier 2

        covenant = _make_court_covenant(leader_sheet=leader)

        with self.assertRaises(CourtGulfViolationError):
            assert_membership_level_allowed(covenant=covenant, character_sheet=servant)

    def test_gulf_enforced_without_mentor_bond_config_seeded(self):
        """Gulf is enforced even when MentorBondConfig is NOT seeded (production default).

        This is the prod-default regression test: the COURT arm runs before the
        MentorBondConfig short-circuit, so unseeded config must never bypass the gulf.
        """
        from world.covenants.models import MentorBondConfig

        # Confirm config is absent — do NOT seed it.
        self.assertFalse(MentorBondConfig.objects.filter(pk=1).exists())

        leader = CharacterSheetFactory()
        servant = CharacterSheetFactory()
        _set_primary_level(leader, 7)  # tier 2
        _set_primary_level(servant, 6)  # tier 2 — same tier → violation

        covenant = _make_court_covenant(leader_sheet=leader)

        with self.assertRaises(CourtGulfViolationError):
            assert_membership_level_allowed(covenant=covenant, character_sheet=servant)

    def test_gulf_allowed_without_mentor_bond_config_seeded(self):
        """Servant one tier below is allowed even when MentorBondConfig is NOT seeded."""
        from world.covenants.models import MentorBondConfig

        self.assertFalse(MentorBondConfig.objects.filter(pk=1).exists())

        leader = CharacterSheetFactory()
        servant = CharacterSheetFactory()
        _set_primary_level(leader, 6)  # tier 2
        _set_primary_level(servant, 5)  # tier 1 — one tier below → allowed

        covenant = _make_court_covenant(leader_sheet=leader)

        # Must not raise
        assert_membership_level_allowed(covenant=covenant, character_sheet=servant)

    def test_servant_higher_tier_than_leader_rejected(self):
        """Servant at a higher tier than leader → CourtGulfViolationError."""
        leader = CharacterSheetFactory()
        servant = CharacterSheetFactory()
        _set_primary_level(leader, 5)  # tier 1
        _set_primary_level(servant, 6)  # tier 2 — above leader

        covenant = _make_court_covenant(leader_sheet=leader)

        with self.assertRaises(CourtGulfViolationError):
            assert_membership_level_allowed(covenant=covenant, character_sheet=servant)

    def test_error_carries_user_message(self):
        """CourtGulfViolationError carries a user_message."""
        leader = CharacterSheetFactory()
        servant = CharacterSheetFactory()
        _set_primary_level(leader, 7)
        _set_primary_level(servant, 6)

        covenant = _make_court_covenant(leader_sheet=leader)

        with self.assertRaises(CourtGulfViolationError) as cm:
            assert_membership_level_allowed(covenant=covenant, character_sheet=servant)

        self.assertTrue(hasattr(cm.exception, "user_message"))
        self.assertIsInstance(cm.exception.user_message, str)
        self.assertGreater(len(cm.exception.user_message), 0)
