"""
Tests for roster serializers.
"""

from contextlib import contextmanager
import logging

from django.test import TestCase
from django.utils import timezone

from world.roster.factories import (
    CharacterFactory,
    PlayerDataFactory,
    RosterEntryFactory,
    RosterTenureFactory,
)
from world.roster.models import ApplicationStatus, RosterApplication


class RosterApplicationCreateSerializerTestCase(TestCase):
    """Test the roster application serializer"""

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

    def test_create_valid_application(self):
        """Test creating a valid application"""
        from world.roster.serializers import RosterApplicationCreateSerializer

        with self.suppress_email_logs():
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
                        "I want to play this character because they're fascinating "
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
        self.assertEqual(app.status, ApplicationStatus.PENDING)
        self.assertEqual(app.player_data, self.player_data)
        self.assertEqual(app.character, self.character)

    def test_application_validation_scenarios(self):
        """Test all scenarios where applications should be rejected"""
        test_cases = [
            {
                "name": "character without roster entry",
                "setup": lambda: CharacterFactory(),
                "character_attr": "setup_result",
                "expected_message": "Character is not on the roster",
            },
            {
                "name": "character already being played",
                "setup": lambda: RosterTenureFactory(
                    roster_entry=self.roster_entry,
                    player_data=self.staff_data,
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
                "setup": lambda: RosterTenureFactory(
                    roster_entry=self.roster_entry,
                    player_data=self.player_data,
                    player_number=1,
                    start_date=timezone.now(),
                    applied_date=timezone.now(),
                    approved_date=timezone.now(),
                    approved_by=self.staff_data,
                ),
                "character_attr": "character",
                "expected_message": "You are already playing this character",
            },
            {
                "name": "roster not accepting applications",
                "setup": lambda: RosterEntryFactory(
                    roster__allow_applications=False
                ).character,
                "character_attr": "setup_result",
                "expected_message": "Player not allowed to apply to this roster type",
            },
        ]

        for case in test_cases:
            with self.subTest(scenario=case["name"]):
                # Clean up any existing applications/tenures for fresh test
                RosterApplication.objects.filter(player_data=self.player_data).delete()
                RosterTenureFactory._meta.model.objects.filter(
                    roster_entry__character=self.character
                ).delete()

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
