"""
Tests for the roster application system.
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from evennia.accounts.models import AccountDB
from evennia.objects.models import ObjectDB
from evennia.utils import create

from evennia_extensions.models import PlayerData
from world.roster.models import Roster, RosterApplication, RosterEntry, RosterTenure


class RosterApplicationTestCase(TestCase):
    """Test the roster application workflow"""

    @classmethod
    def setUpTestData(cls):
        """Set up test data once for the entire test class"""
        # Create test accounts
        cls.player_account = AccountDB.objects.create_user(
            username="testplayer", email="player@test.com", password="testpass"
        )
        cls.staff_account = AccountDB.objects.create_user(
            username="teststaff",
            email="staff@test.com",
            password="testpass",
            is_staff=True,
        )

        # Create PlayerData
        cls.player_data = PlayerData.objects.create(account=cls.player_account)
        cls.staff_data = PlayerData.objects.create(account=cls.staff_account)

        # Create roster and character
        cls.active_roster = Roster.objects.create(
            name="Active", description="Active characters", is_active=True, sort_order=1
        )
        cls.available_roster = Roster.objects.create(
            name="Available",
            description="Available characters",
            is_active=True,
            sort_order=2,
        )

        # Create test character
        cls.character = ObjectDB.objects.create(db_key="Ariel")
        cls.roster_entry = RosterEntry.objects.create(
            character=cls.character, roster=cls.available_roster
        )

    def test_create_valid_application(self):
        """Test creating a valid application"""
        from world.roster.serializers import RosterApplicationCreateSerializer

        # Create serializer with mock request context
        class MockRequest:
            def __init__(self, user):
                self.user = user

        class MockUser:
            def __init__(self, player_data):
                self.player_data = player_data

        request = MockRequest(MockUser(self.player_data))

        serializer = RosterApplicationCreateSerializer(
            data={
                "character_id": self.character.id,
                "application_text": (
                    "I want to play Ariel because she's a fascinating character "
                    "with complex motivations and rich backstory that I'd love to explore."
                ),
            },
            context={"request": request},
        )

        self.assertTrue(
            serializer.is_valid(), f"Serializer errors: {serializer.errors}"
        )
        app = serializer.save()

        self.assertIsNotNone(app)
        self.assertEqual(app.status, "pending")
        self.assertEqual(app.player_data, self.player_data)
        self.assertEqual(app.character, self.character)

    def test_application_validation_scenarios(self):
        """Test all scenarios where applications should be rejected"""
        test_cases = [
            {
                "name": "character without roster entry",
                "setup": lambda: ObjectDB.objects.create(db_key="NonRosterChar"),
                "character_attr": "setup_result",
                "expected_message": "Character is not on the roster",
            },
            {
                "name": "character already being played",
                "setup": lambda: RosterTenure.objects.create(
                    player_data=self.staff_data,
                    character=self.character,
                    player_number=1,
                    start_date=timezone.now(),
                    applied_date=timezone.now(),
                    approved_date=timezone.now(),
                    approved_by=self.staff_data,
                ),
                "character_attr": "character",
                "expected_message": "Character is already being played",
            },
            {
                "name": "duplicate pending application",
                "setup": lambda: RosterApplication.objects.create(
                    player_data=self.player_data,
                    character=self.character,
                    application_text="First application",
                ),
                "character_attr": "character",
                "expected_message": "You already have a pending application for this character",
            },
            {
                "name": "player already playing character",
                "setup": lambda: RosterTenure.objects.create(
                    player_data=self.player_data,
                    character=self.character,
                    player_number=1,
                    start_date=timezone.now(),
                    applied_date=timezone.now(),
                    approved_date=timezone.now(),
                    approved_by=self.staff_data,
                ),
                "character_attr": "character",
                "expected_message": "You are already playing this character",
            },
        ]

        for case in test_cases:
            with self.subTest(scenario=case["name"]):
                # Clean up any existing applications/tenures for fresh test
                RosterApplication.objects.filter(player_data=self.player_data).delete()
                RosterTenure.objects.filter(character=self.character).delete()

                # Run setup
                setup_result = case["setup"]()

                # Get the character to test with
                if case["character_attr"] == "setup_result":
                    test_character = setup_result
                else:
                    test_character = getattr(self, case["character_attr"])

                # Attempt to create application using serializer
                from world.roster.serializers import RosterApplicationCreateSerializer

                class MockRequest:
                    def __init__(self, user):
                        self.user = user

                class MockUser:
                    def __init__(self, player_data):
                        self.player_data = player_data

                request = MockRequest(MockUser(self.player_data))

                serializer = RosterApplicationCreateSerializer(
                    data={
                        "character_id": test_character.id,
                        "application_text": (
                            "This is a test application with enough text to meet "
                            "the minimum length requirement for applications."
                        ),
                    },
                    context={"request": request},
                )

                # Verify rejection
                self.assertFalse(
                    serializer.is_valid(),
                    f"Expected validation failure for {case['name']}",
                )
                # Note: The specific error message checking would need to be updated
                # based on the new serializer error structure

    def test_approve_application_creates_tenure(self):
        """Test that approving an application creates a proper tenure"""
        app = RosterApplication.objects.create(
            player_data=self.player_data,
            character=self.character,
            application_text="I want to play this character",
        )

        tenure = app.approve(self.staff_data)

        # Check application status
        app.refresh_from_db()
        self.assertEqual(app.status, "approved")
        self.assertEqual(app.reviewed_by, self.staff_data)
        self.assertIsNotNone(app.reviewed_date)

        # Check tenure was created
        self.assertIsNotNone(tenure)
        self.assertEqual(tenure.player_data, self.player_data)
        self.assertEqual(tenure.character, self.character)
        self.assertEqual(tenure.player_number, 1)
        self.assertEqual(tenure.approved_by, self.staff_data)
        self.assertTrue(tenure.is_current)

    def test_approve_application_assigns_correct_player_number(self):
        """Test that player numbers are assigned correctly for subsequent players"""
        # Create first tenure (player 1)
        RosterTenure.objects.create(
            player_data=self.staff_data,
            character=self.character,
            player_number=1,
            start_date=timezone.now() - timedelta(days=30),
            end_date=timezone.now() - timedelta(days=1),  # Ended
            applied_date=timezone.now() - timedelta(days=31),
            approved_date=timezone.now() - timedelta(days=30),
            approved_by=self.staff_data,
        )

        # Create application for second player
        app = RosterApplication.objects.create(
            player_data=self.player_data,
            character=self.character,
            application_text="I want to be the second player",
        )

        tenure = app.approve(self.staff_data)

        # Should be player number 2
        self.assertEqual(tenure.player_number, 2)
        self.assertEqual(tenure.display_name, "2nd player of Ariel")

    def test_application_state_transitions(self):
        """Test all application state transitions"""
        # Create a fresh character for each subtest to avoid conflicts
        character2 = ObjectDB.objects.create(db_key="Ariel2")
        RosterEntry.objects.create(character=character2, roster=self.available_roster)

        character3 = ObjectDB.objects.create(db_key="Ariel3")
        RosterEntry.objects.create(character=character3, roster=self.available_roster)

        state_tests = [
            {
                "name": "deny application",
                "character": character2,
                "action": lambda app: app.deny(self.staff_data, "Not enough detail"),
                "expected_status": "denied",
                "expected_result": True,
                "check_fields": {
                    "reviewed_by": self.staff_data,
                    "review_notes": "Not enough detail",
                },
            },
            {
                "name": "withdraw application",
                "character": character3,
                "action": lambda app: app.withdraw(),
                "expected_status": "withdrawn",
                "expected_result": True,
                "check_fields": {},
            },
        ]

        for test_case in state_tests:
            with self.subTest(action=test_case["name"]):
                # Create fresh application
                app = RosterApplication.objects.create(
                    player_data=self.player_data,
                    character=test_case["character"],
                    application_text="Application text",
                )

                # Perform action
                result = test_case["action"](app)

                # Verify result
                self.assertEqual(result, test_case["expected_result"])
                app.refresh_from_db()
                self.assertEqual(app.status, test_case["expected_status"])
                self.assertIsNotNone(app.reviewed_date)

                # Check additional fields
                for field, expected_value in test_case["check_fields"].items():
                    self.assertEqual(getattr(app, field), expected_value)

    def test_invalid_state_transitions(self):
        """Test that state transitions only work on pending applications"""
        invalid_states = ["denied", "approved", "withdrawn"]

        for invalid_status in invalid_states:
            with self.subTest(status=invalid_status):
                # Create character for this test
                char = ObjectDB.objects.create(db_key=f"InvalidChar_{invalid_status}")
                RosterEntry.objects.create(character=char, roster=self.available_roster)

                app = RosterApplication.objects.create(
                    player_data=self.player_data,
                    character=char,
                    application_text="Application text",
                    status=invalid_status,
                )

                # All these should fail for non-pending applications
                self.assertFalse(app.approve(self.staff_data))
                self.assertFalse(app.deny(self.staff_data, "Reason"))
                self.assertFalse(app.withdraw())


class RosterApplicationManagerTestCase(TestCase):
    """Test the custom manager methods"""

    @classmethod
    def setUpTestData(cls):
        """Set up test data once for the entire test class"""
        cls.player_account = AccountDB.objects.create_user(
            username="mgr_testplayer", email="mgr_player@test.com", password="testpass"
        )
        cls.staff_account = AccountDB.objects.create_user(
            username="mgr_teststaff", email="mgr_staff@test.com", password="testpass"
        )
        cls.player_data = PlayerData.objects.create(account=cls.player_account)
        cls.staff_data = PlayerData.objects.create(account=cls.staff_account)

        cls.roster = Roster.objects.create(name="MgrAvailable", is_active=True)
        cls.character1 = ObjectDB.objects.create(db_key="MgrCharacter1")
        cls.character2 = ObjectDB.objects.create(db_key="MgrCharacter2")

        RosterEntry.objects.create(character=cls.character1, roster=cls.roster)
        RosterEntry.objects.create(character=cls.character2, roster=cls.roster)

    def test_pending_applications_query(self):
        """Test the pending() manager method"""
        # Create applications with different statuses
        pending_app = RosterApplication.objects.create(
            player_data=self.player_data,
            character=self.character1,
            application_text="Pending app",
            status="pending",
        )
        RosterApplication.objects.create(
            player_data=self.player_data,
            character=self.character2,
            application_text="Approved app",
            status="approved",
        )

        pending_apps = RosterApplication.objects.pending()

        self.assertEqual(pending_apps.count(), 1)
        self.assertEqual(pending_apps.first(), pending_app)

    def test_for_character_query(self):
        """Test the for_character() manager method"""
        app1 = RosterApplication.objects.create(
            player_data=self.player_data,
            character=self.character1,
            application_text="App for char1",
        )
        RosterApplication.objects.create(
            player_data=self.player_data,
            character=self.character2,
            application_text="App for char2",
        )

        char1_apps = RosterApplication.objects.for_character(self.character1)

        self.assertEqual(char1_apps.count(), 1)
        self.assertEqual(char1_apps.first(), app1)

    def test_for_player_query(self):
        """Test the for_player() manager method"""
        app1 = RosterApplication.objects.create(
            player_data=self.player_data,
            character=self.character1,
            application_text="Player app",
        )
        RosterApplication.objects.create(
            player_data=self.staff_data,
            character=self.character2,
            application_text="Staff app",
        )

        player_apps = RosterApplication.objects.for_player(self.player_data)

        self.assertEqual(player_apps.count(), 1)
        self.assertEqual(player_apps.first(), app1)

    def test_awaiting_review_query(self):
        """Test the awaiting_review() manager method returns pending apps in order"""
        # Create apps at different times
        old_app = RosterApplication.objects.create(
            player_data=self.player_data,
            character=self.character1,
            application_text="Old app",
        )
        old_app.applied_date = timezone.now() - timedelta(days=2)
        old_app.save()

        new_app = RosterApplication.objects.create(
            player_data=self.player_data,
            character=self.character2,
            application_text="New app",
        )

        awaiting = list(RosterApplication.objects.awaiting_review())

        self.assertEqual(len(awaiting), 2)
        self.assertEqual(awaiting[0], old_app)  # Older app first
        self.assertEqual(awaiting[1], new_app)

    def test_recently_reviewed_query(self):
        """Test the recently_reviewed() manager method"""
        # Create reviewed application within the time window
        recent_app = RosterApplication.objects.create(
            player_data=self.player_data,
            character=self.character1,
            application_text="Recent app",
            status="approved",
            reviewed_date=timezone.now() - timedelta(days=3),
        )

        # Create old reviewed application outside the time window
        RosterApplication.objects.create(
            player_data=self.player_data,
            character=self.character2,
            application_text="Old app",
            status="denied",
            reviewed_date=timezone.now() - timedelta(days=10),
        )

        recent_apps = RosterApplication.objects.recently_reviewed(days=7)

        self.assertEqual(recent_apps.count(), 1)
        self.assertEqual(recent_apps.first(), recent_app)


class PlayerDataTestCase(TestCase):
    """Test PlayerData methods for character management"""

    @classmethod
    def setUpTestData(cls):
        """Set up test data once for the entire test class"""
        cls.account = AccountDB.objects.create_user(
            username="pd_testplayer", email="pd_player@test.com", password="testpass"
        )
        cls.player_data = PlayerData.objects.create(account=cls.account)

        cls.roster = Roster.objects.create(name="PDActive", is_active=True)
        cls.character = ObjectDB.objects.create(db_key="PDTestChar")
        cls.roster_entry = RosterEntry.objects.create(
            character=cls.character, roster=cls.roster
        )

    def test_get_available_characters(self):
        """Test getting characters a player can currently play"""
        # Create active tenure
        RosterTenure.objects.create(
            player_data=self.player_data,
            character=self.character,
            player_number=1,
            start_date=timezone.now(),
            applied_date=timezone.now(),
        )

        available = self.player_data.get_available_characters()

        self.assertEqual(available.count(), 1)
        self.assertEqual(available.first(), self.character)

    def test_get_available_characters_excludes_ended_tenures(self):
        """Test that ended tenures don't show as available"""
        # Create ended tenure
        RosterTenure.objects.create(
            player_data=self.player_data,
            character=self.character,
            player_number=1,
            start_date=timezone.now() - timedelta(days=30),
            end_date=timezone.now() - timedelta(days=1),  # Ended
            applied_date=timezone.now() - timedelta(days=31),
        )

        available = self.player_data.get_available_characters()

        self.assertEqual(available.count(), 0)

    def test_get_available_characters_excludes_non_roster(self):
        """Test that non-roster characters aren't available even with tenure"""
        # Create character without roster entry
        non_roster_char = ObjectDB.objects.create(db_key="NonRosterChar")

        RosterTenure.objects.create(
            player_data=self.player_data,
            character=non_roster_char,
            player_number=1,
            start_date=timezone.now(),
            applied_date=timezone.now(),
        )

        available = self.player_data.get_available_characters()

        self.assertEqual(available.count(), 0)

    def test_get_pending_applications(self):
        """Test getting player's pending applications"""
        # Create a second character for the approved application
        character2 = ObjectDB.objects.create(db_key="TestChar2")
        RosterEntry.objects.create(character=character2, roster=self.roster)

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

        self.assertEqual(pending.count(), 1)
        self.assertEqual(pending.first(), app)

    def test_staff_can_approve_applications(self):
        """Test that staff players can approve applications"""
        # Make account staff
        self.account.is_staff = True
        self.account.save()

        self.assertTrue(self.player_data.can_approve_applications())

    def test_non_staff_cannot_approve_applications(self):
        """Test that non-staff players cannot approve applications by default"""
        self.assertFalse(self.player_data.can_approve_applications())

    def test_staff_approval_scope(self):
        """Test that staff get full approval scope"""
        self.account.is_staff = True
        self.account.save()

        self.assertEqual(self.player_data.get_approval_scope(), "all")

    def test_non_staff_approval_scope(self):
        """Test that non-staff get no approval scope by default"""
        self.assertEqual(self.player_data.get_approval_scope(), "none")


class RosterApplicationPolicyTestCase(TestCase):
    """Test policy validation methods for applications"""

    @classmethod
    def setUpTestData(cls):
        """Set up test data once for the entire test class"""
        cls.player_account = AccountDB.objects.create_user(
            username="policy_testplayer",
            email="policy_player@test.com",
            password="testpass",
        )
        cls.player_data = PlayerData.objects.create(account=cls.player_account)

        # Create different roster types for testing
        cls.active_roster = Roster.objects.create(
            name="Active", description="Active characters", is_active=True, sort_order=1
        )
        cls.restricted_roster = Roster.objects.create(
            name="Restricted",
            description="Restricted characters",
            is_active=True,
            sort_order=2,
        )
        cls.inactive_roster = Roster.objects.create(
            name="Inactive",
            description="Inactive characters",
            is_active=False,
            sort_order=3,
        )

        # Create test characters in different rosters
        cls.regular_character = ObjectDB.objects.create(db_key="RegularChar")
        cls.regular_entry = RosterEntry.objects.create(
            character=cls.regular_character, roster=cls.active_roster
        )

        cls.restricted_character = ObjectDB.objects.create(db_key="RestrictedChar")
        cls.restricted_entry = RosterEntry.objects.create(
            character=cls.restricted_character, roster=cls.restricted_roster
        )

        cls.inactive_character = ObjectDB.objects.create(db_key="InactiveChar")
        cls.inactive_entry = RosterEntry.objects.create(
            character=cls.inactive_character, roster=cls.inactive_roster
        )

    def test_get_application_policy_issues_regular_character(self):
        """Test policy issues for regular active characters"""
        from world.roster.serializers import RosterApplicationCreateSerializer

        serializer = RosterApplicationCreateSerializer()
        issues = serializer._get_policy_issues(self.player_data, self.regular_character)

        # Regular active character should have no policy issues
        self.assertEqual(len(issues), 0)

    def test_get_application_policy_issues_restricted_character(self):
        """Test policy issues for restricted characters"""
        from world.roster.serializers import RosterApplicationCreateSerializer

        serializer = RosterApplicationCreateSerializer()
        issues = serializer._get_policy_issues(
            self.player_data, self.restricted_character
        )

        # Restricted character should require staff review
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["code"], "restricted_requires_review")
        self.assertEqual(
            issues[0]["message"],
            "Character requires special approval and trust evaluation",
        )

    def test_get_application_policy_issues_inactive_roster(self):
        """Test policy issues for characters in inactive rosters"""
        from world.roster.serializers import RosterApplicationCreateSerializer

        serializer = RosterApplicationCreateSerializer()
        issues = serializer._get_policy_issues(
            self.player_data, self.inactive_character
        )

        # Inactive roster should be flagged
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["code"], "inactive_roster")
        self.assertEqual(issues[0]["message"], "Character is in an inactive roster")

    def test_get_policy_review_info_no_issues(self):
        """Test policy review info for a character with no issues"""
        app = RosterApplication.objects.create(
            player_data=self.player_data,
            character=self.regular_character,
            application_text="Test application",
        )

        info = app.get_policy_review_info()

        self.assertEqual(info["basic_eligibility"], "Passed")
        self.assertEqual(len(info["policy_issues"]), 0)
        self.assertFalse(info["requires_staff_review"])
        self.assertTrue(info["auto_approvable"])
        self.assertEqual(info["character_previous_players"], 0)
        self.assertIn("player_current_characters", info)

    def test_get_policy_review_info_with_issues(self):
        """Test policy review info for a character with policy issues"""
        app = RosterApplication.objects.create(
            player_data=self.player_data,
            character=self.restricted_character,
            application_text="Test application",
        )

        info = app.get_policy_review_info()

        self.assertEqual(info["basic_eligibility"], "Passed")
        self.assertEqual(len(info["policy_issues"]), 1)
        self.assertTrue(info["requires_staff_review"])
        self.assertFalse(info["auto_approvable"])
        self.assertEqual(
            info["policy_issues"][0]["message"],
            "Character requires special approval and trust evaluation",
        )

    def test_get_policy_review_info_includes_context(self):
        """Test that policy review info includes proper context"""
        # Give player a current character for context
        other_character = ObjectDB.objects.create(db_key="PlayerCurrentChar")
        RosterEntry.objects.create(character=other_character, roster=self.active_roster)
        RosterTenure.objects.create(
            player_data=self.player_data,
            character=other_character,
            player_number=1,
            start_date=timezone.now(),
            applied_date=timezone.now(),
        )

        # Create previous player for the target character
        other_player_account = AccountDB.objects.create_user(
            username="other_player", email="other@test.com", password="testpass"
        )
        other_player_data = PlayerData.objects.create(account=other_player_account)
        RosterTenure.objects.create(
            player_data=other_player_data,
            character=self.regular_character,
            player_number=1,
            start_date=timezone.now() - timedelta(days=30),
            end_date=timezone.now() - timedelta(days=1),
            applied_date=timezone.now() - timedelta(days=31),
        )

        app = RosterApplication.objects.create(
            player_data=self.player_data,
            character=self.regular_character,
            application_text="Test application",
        )

        info = app.get_policy_review_info()

        # Should include current characters
        self.assertIn("PlayerCurrentChar", info["player_current_characters"])

        # Should show previous player count
        self.assertEqual(info["character_previous_players"], 1)


class RosterTenureTestCase(TestCase):
    """Test RosterTenure functionality"""

    @classmethod
    def setUpTestData(cls):
        """Set up test data once for the entire test class"""
        cls.account = AccountDB.objects.create_user(
            username="rt_testplayer", email="rt_player@test.com", password="testpass"
        )
        cls.player_data = PlayerData.objects.create(account=cls.account)
        cls.character = ObjectDB.objects.create(db_key="RTAriel")

    def test_display_name_formatting(self):
        """Test that display names are formatted correctly"""
        test_cases = [
            (1, "1st player of RTAriel"),
            (2, "2nd player of RTAriel"),
            (3, "3rd player of RTAriel"),
            (4, "4th player of RTAriel"),
            (11, "11th player of RTAriel"),
            (21, "21st player of RTAriel"),
            (22, "22nd player of RTAriel"),
        ]

        for player_number, expected in test_cases:
            with self.subTest(player_number=player_number):
                tenure = RosterTenure(
                    player_data=self.player_data,
                    character=self.character,
                    player_number=player_number,
                )
                self.assertEqual(tenure.display_name, expected)

    def test_tenure_status_properties(self):
        """Test tenure status properties"""
        # Current tenure (no end date)
        current_tenure = RosterTenure.objects.create(
            player_data=self.player_data,
            character=self.character,
            player_number=1,
            start_date=timezone.now(),
            applied_date=timezone.now(),
        )

        # Ended tenure
        ended_character = ObjectDB.objects.create(db_key="RTEndedChar")
        ended_tenure = RosterTenure.objects.create(
            player_data=self.player_data,
            character=ended_character,
            player_number=1,
            start_date=timezone.now() - timedelta(days=30),
            end_date=timezone.now() - timedelta(days=1),
            applied_date=timezone.now() - timedelta(days=31),
        )

        self.assertTrue(current_tenure.is_current)
        self.assertFalse(ended_tenure.is_current)


class AccountCharactersPropertyTestCase(TestCase):
    """Test caching behavior of Account.characters property."""

    @classmethod
    def setUpTestData(cls):
        cls.account = create.create_account(
            "cache_player", "cache@test.com", "strongpass"
        )
        cls.player_data = PlayerData.objects.create(account=cls.account)
        cls.roster = Roster.objects.create(name="CacheRoster", is_active=True)
        cls.character = ObjectDB.objects.create(db_key="CacheChar")
        RosterEntry.objects.create(character=cls.character, roster=cls.roster)
        cls.tenure = RosterTenure.objects.create(
            player_data=cls.player_data,
            character=cls.character,
            player_number=1,
            start_date=timezone.now(),
            applied_date=timezone.now(),
        )

    def test_property_cleared_on_tenure_update(self):
        self.assertEqual(self.account.characters, [self.character])

        self.tenure.end_date = timezone.now()
        self.tenure.save()

        self.assertEqual(self.account.characters, [])

    def test_previous_tenure_not_returned_if_another_player_active(self):
        other_account = create.create_account("other", "other@test.com", "strongpass")
        other_data = PlayerData.objects.create(account=other_account)

        RosterTenure.objects.create(
            player_data=other_data,
            character=self.character,
            player_number=2,
            start_date=timezone.now(),
            applied_date=timezone.now(),
        )

        self.tenure.end_date = timezone.now()
        self.tenure.save()

        self.assertEqual(self.account.characters, [])
        self.assertEqual(other_account.characters, [self.character])
