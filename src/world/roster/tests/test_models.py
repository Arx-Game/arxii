"""
Tests for roster models.
"""

from contextlib import contextmanager
from datetime import timedelta
import logging

from django.test import TestCase
from django.utils import timezone
from evennia.utils import create

from world.roster.factories import (
    CharacterFactory,
    PlayerDataFactory,
    RosterEntryFactory,
    RosterTenureFactory,
)
from world.roster.models import ApplicationStatus, RosterApplication


class RosterApplicationModelTestCase(TestCase):
    """Test RosterApplication model methods"""

    @contextmanager
    def suppress_email_logs(self):
        """Context manager to suppress email service logging during tests"""
        email_logger = logging.getLogger("world.roster.email_service")
        original_level = email_logger.level
        email_logger.setLevel(logging.ERROR)
        try:
            yield
        finally:
            email_logger.setLevel(original_level)

    def setUp(self):
        """Set up test data for each test"""
        self.player_data = PlayerDataFactory()
        self.staff_data = PlayerDataFactory(account__is_staff=True)
        self.character = CharacterFactory()
        self.roster_entry = RosterEntryFactory(character=self.character)

    def test_approve_application_creates_tenure(self):
        """Test that approving an application creates a proper tenure"""
        with self.suppress_email_logs():
            app = RosterApplication.objects.create(
                player_data=self.player_data,
                character=self.character,
                application_text="I want to play this character",
            )

            tenure = app.approve(self.staff_data)

        # Check application status
        app.refresh_from_db()
        assert app.status == ApplicationStatus.APPROVED
        assert app.reviewed_by == self.staff_data
        assert app.reviewed_date is not None

        # Check tenure was created
        assert tenure is not None
        assert tenure.player_data == self.player_data
        assert tenure.character == self.character
        assert tenure.player_number == 1
        assert tenure.approved_by == self.staff_data
        assert tenure.is_current

    def test_approve_application_assigns_correct_player_number(self):
        """Test that player numbers are assigned correctly for subsequent players"""
        with self.suppress_email_logs():
            # Create first tenure (player 1)
            RosterTenureFactory(
                roster_entry=self.roster_entry,
                player_number=1,
                start_date=timezone.now() - timedelta(days=30),
                end_date=timezone.now() - timedelta(days=1),  # Ended
                applied_date=timezone.now() - timedelta(days=31),
            )

            # Create application for second player
            app = RosterApplication.objects.create(
                player_data=self.player_data,
                character=self.character,
                application_text="I want to be the second player",
            )

            tenure = app.approve(self.staff_data)

        # Should be player number 2
        assert tenure.player_number == 2
        assert tenure.display_name == f"2nd player of {self.character.name}"

    def test_application_state_transitions(self):
        """Test all application state transitions"""
        # Create fresh characters for each subtest to avoid conflicts
        character2 = CharacterFactory()
        RosterEntryFactory(character=character2)

        character3 = CharacterFactory()
        RosterEntryFactory(character=character3)

        state_tests = [
            {
                "name": "deny application",
                "character": character2,
                "action": lambda app: app.deny(self.staff_data, "Not enough detail"),
                "expected_status": ApplicationStatus.DENIED,
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
                "expected_status": ApplicationStatus.WITHDRAWN,
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
                assert result == test_case["expected_result"]
                app.refresh_from_db()
                assert app.status == test_case["expected_status"]
                assert app.reviewed_date is not None

                # Check additional fields
                for field, expected_value in test_case["check_fields"].items():
                    assert getattr(app, field) == expected_value

    def test_invalid_state_transitions(self):
        """Test that state transitions only work on pending applications"""
        invalid_states = [
            ApplicationStatus.DENIED,
            ApplicationStatus.APPROVED,
            ApplicationStatus.WITHDRAWN,
        ]

        for invalid_status in invalid_states:
            with self.subTest(status=invalid_status):
                # Create character for this test
                char = CharacterFactory()
                RosterEntryFactory(character=char)

                app = RosterApplication.objects.create(
                    player_data=self.player_data,
                    character=char,
                    application_text="Application text",
                    status=invalid_status,
                )

                # All these should fail for non-pending applications
                assert not app.approve(self.staff_data)
                assert not app.deny(self.staff_data, "Reason")
                assert not app.withdraw()


class RosterEntryModelTestCase(TestCase):
    """Test RosterEntry model helpers."""

    def test_current_tenure_returns_unended(self):
        entry = RosterEntryFactory()
        RosterTenureFactory(
            roster_entry=entry,
            end_date=timezone.now(),
            player_number=1,
        )
        current = RosterTenureFactory(roster_entry=entry, player_number=2)
        assert entry.current_tenure == current

    def test_accepts_applications_conditions(self):
        entry = RosterEntryFactory()
        assert entry.accepts_applications

        RosterTenureFactory(roster_entry=entry)
        del entry.cached_tenures
        assert not entry.accepts_applications

        disallowed = RosterEntryFactory(roster__allow_applications=False)
        assert not disallowed.accepts_applications


class RosterTenureModelTestCase(TestCase):
    """Test RosterTenure model functionality"""

    def setUp(self):
        """Set up test data for each test"""
        self.player_data = PlayerDataFactory()
        self.character = CharacterFactory()
        self.roster_entry = RosterEntryFactory(character=self.character)

    def test_display_name_formatting(self):
        """Test that display names are formatted correctly"""
        test_cases = [
            (1, f"1st player of {self.character.name}"),
            (2, f"2nd player of {self.character.name}"),
            (3, f"3rd player of {self.character.name}"),
            (4, f"4th player of {self.character.name}"),
            (11, f"11th player of {self.character.name}"),
            (21, f"21st player of {self.character.name}"),
            (22, f"22nd player of {self.character.name}"),
        ]

        for player_number, expected in test_cases:
            with self.subTest(player_number=player_number):
                tenure = RosterTenureFactory.build(
                    player_data=self.player_data,
                    roster_entry=self.roster_entry,
                    player_number=player_number,
                )
                assert tenure.display_name == expected

    def test_tenure_status_properties(self):
        """Test tenure status properties"""
        # Current tenure (no end date)
        current_tenure = RosterTenureFactory(
            player_data=self.player_data,
            roster_entry=self.roster_entry,
            player_number=1,
        )

        # Ended tenure
        ended_tenure = RosterTenureFactory(
            player_data=self.player_data,
            roster_entry=self.roster_entry,
            player_number=2,
            start_date=timezone.now() - timedelta(days=30),
            end_date=timezone.now() - timedelta(days=1),
        )

        assert current_tenure.is_current
        assert not ended_tenure.is_current


class AccountCharactersPropertyTestCase(TestCase):
    """Test caching behavior of Account.characters property."""

    def setUp(self):
        """Set up test data for each test"""
        self.account = create.create_account(
            "cache_player",
            "cache@test.com",
            "strongpass",
        )
        self.player_data = PlayerDataFactory(account=self.account)
        self.character = CharacterFactory()
        self.roster_entry = RosterEntryFactory(character=self.character)
        self.tenure = RosterTenureFactory(
            player_data=self.player_data,
            roster_entry=self.roster_entry,
        )

    def test_property_cleared_on_tenure_update(self):
        assert self.account.characters == [self.character]

        self.tenure.end_date = timezone.now()
        self.tenure.save()

        assert self.account.characters == []

    def test_previous_tenure_not_returned_if_another_player_active(self):
        other_account = create.create_account("other", "other@test.com", "strongpass")
        other_data = PlayerDataFactory(account=other_account)

        RosterTenureFactory(
            player_data=other_data,
            roster_entry=self.roster_entry,
            player_number=2,
        )

        self.tenure.end_date = timezone.now()
        self.tenure.save()

        assert self.account.characters == []
        assert other_account.characters == [self.character]
