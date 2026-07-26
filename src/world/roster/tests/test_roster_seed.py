"""One seeding path, one row per shelf (#2728)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import PlayerDataFactory, RosterEntryFactory
from world.roster.models import Roster
from world.roster.models.choices import ActivityRequirement, RosterType, ValidationErrorCodes
from world.roster.policy_service import RosterPolicyService
from world.roster.seeds import ensure_rosters


class EnsureRostersTests(TestCase):
    def test_creates_every_roster_type_exactly_once(self):
        ensure_rosters()
        self.assertEqual(Roster.objects.count(), len(RosterType.values))
        for value in RosterType.values:
            self.assertEqual(Roster.objects.filter(roster_type=value).count(), 1)

    def test_is_idempotent(self):
        ensure_rosters()
        ensure_rosters()
        self.assertEqual(Roster.objects.count(), len(RosterType.values))

    def test_activity_requirement_is_set_so_the_sweep_is_reachable(self):
        """The sweep filters on this; leaving it at NONE made the feature inert."""
        rosters = ensure_rosters()
        self.assertEqual(rosters[RosterType.ACTIVE].activity_requirement, ActivityRequirement.HIGH)

    def test_npc_and_active_refuse_applications(self):
        rosters = ensure_rosters()
        self.assertFalse(rosters[RosterType.NPC].allow_applications)
        self.assertFalse(rosters[RosterType.ACTIVE].allow_applications)
        self.assertTrue(rosters[RosterType.AVAILABLE].allow_applications)


class RestrictedGateTests(TestCase):
    """`RosterPolicyService.get_policy_issues` is the public entry point (confirmed
    via `grep -n "^def \\|^    def " world/roster/policy_service.py` — there is no
    module-level `validate_character_policy`)."""

    def test_restricted_gate_fires(self):
        """The gate matched a roster nothing ever created, so it never fired (#2728)."""
        rosters = ensure_rosters()
        sheet = CharacterSheetFactory()
        RosterEntryFactory(character_sheet=sheet, roster=rosters[RosterType.RESTRICTED])
        player_data = PlayerDataFactory()

        issues = RosterPolicyService.get_policy_issues(player_data, sheet)
        codes = [issue["code"] for issue in issues]
        self.assertIn(ValidationErrorCodes.RESTRICTED_REQUIRES_REVIEW, codes)

    def test_available_roster_does_not_trip_the_gate(self):
        rosters = ensure_rosters()
        sheet = CharacterSheetFactory()
        RosterEntryFactory(character_sheet=sheet, roster=rosters[RosterType.AVAILABLE])
        player_data = PlayerDataFactory()

        issues = RosterPolicyService.get_policy_issues(player_data, sheet)
        codes = [issue["code"] for issue in issues]
        self.assertNotIn(ValidationErrorCodes.RESTRICTED_REQUIRES_REVIEW, codes)
