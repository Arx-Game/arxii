"""
Tests for roster services and business logic.
"""

from django.test import TestCase

from world.roster.factories import (
    CharacterFactory,
    PlayerDataFactory,
    RosterEntryFactory,
    RosterFactory,
)
from world.roster.models import RosterApplication


class PlayerDataServiceTestCase(TestCase):
    """Test PlayerData methods for character management"""

    def setUp(self):
        """Set up test data for each test"""
        self.player_data = PlayerDataFactory()
        self.character = CharacterFactory()
        self.roster = RosterFactory(is_active=True)
        self.roster_entry = RosterEntryFactory(
            character=self.character,
            roster=self.roster,
        )

    def test_get_available_characters(self):
        """Test getting characters a player can currently play"""
        from world.roster.factories import RosterTenureFactory

        # Create active tenure
        RosterTenureFactory(
            player_data=self.player_data,
            roster_entry=self.roster_entry,
            player_number=1,
        )

        available = self.player_data.get_available_characters()

        assert len(available) == 1
        assert available[0] == self.character

    def test_get_available_characters_excludes_ended_tenures(self):
        """Test that ended tenures don't show as available"""
        from datetime import timedelta

        from django.utils import timezone

        from world.roster.factories import RosterTenureFactory

        # Create ended tenure
        RosterTenureFactory(
            player_data=self.player_data,
            roster_entry=self.roster_entry,
            player_number=1,
            start_date=timezone.now() - timedelta(days=30),
            end_date=timezone.now() - timedelta(days=1),  # Ended
        )

        available = self.player_data.get_available_characters()

        assert len(available) == 0

    def test_get_available_characters_excludes_non_roster(self):
        """Test that non-roster characters aren't available even with tenure"""
        from world.roster.factories import RosterTenureFactory

        # Create character with roster entry in inactive roster
        non_roster_char = CharacterFactory()
        inactive_roster = RosterFactory(is_active=False)
        non_roster_entry = RosterEntryFactory(
            character=non_roster_char,
            roster=inactive_roster,
        )

        RosterTenureFactory(
            player_data=self.player_data,
            roster_entry=non_roster_entry,
            player_number=1,
        )

        available = self.player_data.get_available_characters()

        assert len(available) == 0

    def test_get_pending_applications(self):
        """Test getting player's pending applications"""
        # Create a second character for the approved application
        character2 = CharacterFactory()
        RosterEntryFactory(character=character2, roster=self.roster)

        # Create pending application
        app = RosterApplication.objects.create(
            player_data=self.player_data,
            character=self.character,
            application_text="Test application",
        )

        # Create approved application for different character (should not be included)
        RosterApplication.objects.create(
            player_data=self.player_data,
            character=character2,
            application_text="Approved app",
            status="approved",
        )

        pending = self.player_data.get_pending_applications()

        assert pending.count() == 1
        assert pending.first() == app

    def test_staff_can_approve_applications(self):
        """Test that staff players can approve applications"""
        # Make account staff
        self.player_data.account.is_staff = True
        self.player_data.account.save()

        assert self.player_data.can_approve_applications()

    def test_non_staff_cannot_approve_applications(self):
        """Test that non-staff players cannot approve applications by default"""
        assert not self.player_data.can_approve_applications()

    def test_staff_approval_scope(self):
        """Test that staff get full approval scope"""
        self.player_data.account.is_staff = True
        self.player_data.account.save()

        assert self.player_data.get_approval_scope() == "all"

    def test_non_staff_approval_scope(self):
        """Test that non-staff get no approval scope by default"""
        assert self.player_data.get_approval_scope() == "none"


class RosterPolicyServiceTestCase(TestCase):
    """Test policy validation methods for applications"""

    def setUp(self):
        """Set up test data for each test"""
        self.player_data = PlayerDataFactory()

        # Create different roster types for testing
        self.active_roster = RosterFactory(name="Active", is_active=True, sort_order=1)
        self.restricted_roster = RosterFactory(
            name="Restricted",
            is_active=True,
            sort_order=2,
        )
        self.inactive_roster = RosterFactory(
            name="Inactive",
            is_active=False,
            sort_order=3,
        )

        # Create test characters in different rosters
        self.regular_character = CharacterFactory()
        self.regular_entry = RosterEntryFactory(
            character=self.regular_character,
            roster=self.active_roster,
        )

        self.restricted_character = CharacterFactory()
        self.restricted_entry = RosterEntryFactory(
            character=self.restricted_character,
            roster=self.restricted_roster,
        )

        self.inactive_character = CharacterFactory()
        self.inactive_entry = RosterEntryFactory(
            character=self.inactive_character,
            roster=self.inactive_roster,
        )

    def test_get_application_policy_issues_regular_character(self):
        """Test policy issues for regular active characters"""
        from world.roster.serializers import RosterApplicationCreateSerializer

        serializer = RosterApplicationCreateSerializer()
        issues = serializer._get_policy_issues(self.player_data, self.regular_character)

        # Regular active character should have no policy issues
        assert len(issues) == 0

    def test_get_application_policy_issues_restricted_character(self):
        """Test policy issues for restricted characters"""
        from world.roster.serializers import RosterApplicationCreateSerializer

        serializer = RosterApplicationCreateSerializer()
        issues = serializer._get_policy_issues(
            self.player_data,
            self.restricted_character,
        )

        # Restricted character should require staff review
        assert len(issues) == 1
        assert issues[0]["code"] == "restricted_requires_review"
        assert (
            issues[0]["message"]
            == "Character requires special approval and trust evaluation"
        )

    def test_get_application_policy_issues_inactive_roster(self):
        """Test policy issues for characters in inactive rosters"""
        from world.roster.serializers import RosterApplicationCreateSerializer

        serializer = RosterApplicationCreateSerializer()
        issues = serializer._get_policy_issues(
            self.player_data,
            self.inactive_character,
        )

        # Inactive roster should be flagged
        assert len(issues) == 1
        assert issues[0]["code"] == "inactive_roster"
        assert issues[0]["message"] == "Character is in an inactive roster"

    def test_get_policy_review_info_no_issues(self):
        """Test policy review info for a character with no issues"""
        app = RosterApplication.objects.create(
            player_data=self.player_data,
            character=self.regular_character,
            application_text="Test application",
        )

        info = app.get_policy_review_info()

        assert info["basic_eligibility"] == "Passed"
        assert len(info["policy_issues"]) == 0
        assert not info["requires_staff_review"]
        assert info["auto_approvable"]
        assert info["character_previous_players"] == 0
        assert "player_current_characters" in info

    def test_get_policy_review_info_with_issues(self):
        """Test policy review info for a character with policy issues"""
        app = RosterApplication.objects.create(
            player_data=self.player_data,
            character=self.restricted_character,
            application_text="Test application",
        )

        info = app.get_policy_review_info()

        assert info["basic_eligibility"] == "Passed"
        assert len(info["policy_issues"]) == 1
        assert info["requires_staff_review"]
        assert not info["auto_approvable"]
        assert (
            info["policy_issues"][0]["message"]
            == "Character requires special approval and trust evaluation"
        )

    def test_get_policy_review_info_includes_context(self):
        """Test that policy review info includes proper context"""
        from datetime import timedelta

        from django.utils import timezone

        from world.roster.factories import RosterTenureFactory

        # Give player a current character for context
        other_character = CharacterFactory()
        other_roster_entry = RosterEntryFactory(
            character=other_character,
            roster=self.active_roster,
        )
        RosterTenureFactory(
            player_data=self.player_data,
            roster_entry=other_roster_entry,
            player_number=1,
        )

        # Create previous player for the target character
        other_player_data = PlayerDataFactory()
        RosterTenureFactory(
            player_data=other_player_data,
            roster_entry=self.regular_entry,
            player_number=1,
            start_date=timezone.now() - timedelta(days=30),
            end_date=timezone.now() - timedelta(days=1),
        )

        app = RosterApplication.objects.create(
            player_data=self.player_data,
            character=self.regular_character,
            application_text="Test application",
        )

        info = app.get_policy_review_info()

        # Should include current characters
        assert other_character.name in info["player_current_characters"]

        # Should show previous player count
        assert info["character_previous_players"] == 1
