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
from world.roster.serializers import RosterEntrySerializer


class CharacterSerializerTestCase(TestCase):
    """Test the CharacterSerializer, including race field."""

    def setUp(self):
        """Set up test data."""
        # Import here to avoid circular imports
        from world.character_sheets.models import Race

        self.character = CharacterFactory()
        # Use existing race from data migration, or create a test-specific one
        try:
            self.race = Race.objects.get(name="Human")
        except Race.DoesNotExist:
            from world.character_sheets.factories import RaceFactory

            self.race = RaceFactory(name="TestRace", description="A test race")

        # Create a test subrace
        from world.character_sheets.factories import SubraceFactory

        self.subrace = SubraceFactory(
            race=self.race,
            name="TestSubrace",
            description="A test subrace",
        )

    def test_race_serialization_with_race_and_subrace(self):
        """Test that race field includes both race and subrace data."""
        from world.character_sheets.factories import CharacterSheetFactory
        from world.roster.serializers import CharacterSerializer

        # Create character sheet with race and subrace
        CharacterSheetFactory(
            character=self.character,
            race=self.race,
            subrace=self.subrace,
        )

        serializer = CharacterSerializer(instance=self.character)
        data = serializer.data

        # Check race field structure
        assert data["race"] is not None
        assert "race" in data["race"]
        assert "subrace" in data["race"]

        # Check race data
        race_data = data["race"]["race"]
        assert race_data["id"] == self.race.id
        assert race_data["name"] == self.race.name
        assert race_data["description"] == self.race.description

        # Check subrace data
        subrace_data = data["race"]["subrace"]
        assert subrace_data["id"] == self.subrace.id
        assert subrace_data["name"] == self.subrace.name
        assert subrace_data["description"] == self.subrace.description
        assert subrace_data["race"] == self.race.name

    def test_race_serialization_with_race_only(self):
        """Test that race field works with only race, no subrace."""
        from world.character_sheets.factories import CharacterSheetFactory
        from world.roster.serializers import CharacterSerializer

        # Create character sheet with race only
        CharacterSheetFactory(character=self.character, race=self.race, subrace=None)

        serializer = CharacterSerializer(instance=self.character)
        data = serializer.data

        # Check race field structure
        assert data["race"] is not None
        assert "race" in data["race"]
        assert "subrace" in data["race"]

        # Check race data
        race_data = data["race"]["race"]
        assert race_data["name"] == self.race.name

        # Check subrace is None
        assert data["race"]["subrace"] is None

    def test_all_character_serializer_fields_with_populated_data(self):
        """
        Test CharacterSerializer fields with populated data for serialization errors.
        """
        from world.character_sheets.factories import (
            CharacterSheetFactory,
            ObjectDisplayDataFactory,
        )
        from world.roster.serializers import CharacterSerializer

        # Create character with comprehensive data
        character = CharacterFactory(db_key="TestCharacter")

        # Create sheet with all item_data fields populated
        CharacterSheetFactory(
            character=character,
            age=28,
            gender="female",
            race=self.race,
            subrace=self.subrace,
            concept="A skilled warrior-diplomat",
            family="House Testington",
            vocation="Knight-Captain",
            social_rank=7,
            background=(
                "Born to nobility, trained in both combat and diplomacy from a "
                "young age."
            ),
        )

        # Create display data
        ObjectDisplayDataFactory(
            object=character,
            longname="Dame TestCharacter the Bold",
        )

        # Test serialization of ALL fields
        serializer = CharacterSerializer(instance=character)
        data = serializer.data

        # Verify all field types and values
        assert isinstance(data, dict)

        # Basic fields
        assert data["id"] == character.id
        assert data["name"] == "TestCharacter"

        # item_data sourced fields - these are the ones that could cause issubclass
        # errors
        assert data["age"] == 28
        assert data["gender"] == "female"
        assert data["concept"] == "A skilled warrior-diplomat"
        assert data["family"] == "House Testington"
        assert data["vocation"] == "Knight-Captain"
        assert data["social_rank"] == 7
        assert (
            data["background"]
            == "Born to nobility, trained in both combat and diplomacy from a young age."
        )

        # SerializerMethodField fields
        assert data["race"] is not None
        assert data["char_class"] is None  # Placeholder
        assert data["level"] is None  # Placeholder

        # Default list fields
        assert data["relationships"] == []
        assert data["galleries"] == []

        # Verify race field structure (already tested above but include for completeness)
        race_data = data["race"]
        assert "race" in race_data
        assert "subrace" in race_data
        assert race_data["race"]["name"] == self.race.name
        assert race_data["subrace"]["name"] == self.subrace.name

    def test_character_serializer_with_missing_sheet_data(self):
        """Test CharacterSerializer handles missing/empty sheet data gracefully."""
        from world.roster.serializers import CharacterSerializer

        # Create character without explicit sheet data (will get defaults)
        character = CharacterFactory()

        # Should not raise any errors during serialization
        serializer = CharacterSerializer(instance=character)
        data = serializer.data

        # Should return reasonable defaults
        assert isinstance(data, dict)
        assert data["name"] == character.db_key
        assert isinstance(data["age"], int)  # Should get default age
        assert isinstance(data["gender"], str)  # Should get default gender
        assert data["concept"] == ""
        assert data["family"] == ""
        assert data["vocation"] == ""
        assert isinstance(data["social_rank"], int)  # Should get default
        assert data["background"] == ""
        assert data["relationships"] == []
        assert data["galleries"] == []

        # Race should return empty structure
        assert data["race"] is not None
        assert data["race"]["race"] is None
        assert data["race"]["subrace"] is None

    def test_race_serialization_no_sheet_data(self):
        """Test that race field returns empty structure when character has default sheet."""
        from world.roster.serializers import CharacterSerializer

        # Create a character - it will have a default sheet but no race
        fresh_character = CharacterFactory()

        serializer = CharacterSerializer(instance=fresh_character)
        data = serializer.data

        # Should return structure with None values
        assert data["race"] is not None
        assert data["race"]["race"] is None
        assert data["race"]["subrace"] is None

    def test_race_serialization_no_race_data(self):
        """Test that race field returns empty structure when sheet has no race."""
        from world.character_sheets.factories import CharacterSheetFactory
        from world.roster.serializers import CharacterSerializer

        # Create character sheet without race
        CharacterSheetFactory(character=self.character, race=None, subrace=None)

        serializer = CharacterSerializer(instance=self.character)
        data = serializer.data

        # Check race field structure
        assert data["race"] is not None
        assert data["race"]["race"] is None
        assert data["race"]["subrace"] is None


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

            assert serializer.is_valid(), f"Serializer errors: {serializer.errors}"
            app = serializer.save()

        assert app is not None
        assert app.status == ApplicationStatus.PENDING
        assert app.player_data == self.player_data
        assert app.character == self.character

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
                    roster__allow_applications=False,
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
                    roster_entry__character=self.character,
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
        assert not serializer.is_valid(), (
            f"Expected validation failure for {case['name']}"
        )


class RosterEntrySerializerTestCase(TestCase):
    """Test the roster entry serializer."""

    def setUp(self):
        """Create a roster entry for testing."""
        self.entry = RosterEntryFactory()

        # Populate sheet data
        sheet = self.entry.character.item_data._get_sheet()
        sheet.quote = "Honor above all"
        sheet.save()

        display = self.entry.character.item_data._get_display_data()
        display.longname = "Sir TestChar the Bold"
        display.permanent_description = "A stalwart knight"
        display.save()

    def _serialize(self, request_user):
        """Helper to serialize with a mock request."""

        class MockRequest:
            user = request_user

        return RosterEntrySerializer(
            self.entry,
            context={"request": MockRequest()},
        ).data

    def test_includes_fullname_quote_description(self):
        """Serializer exposes additional character fields."""

        user = type("User", (), {"is_authenticated": True})()
        data = self._serialize(user)

        assert data["fullname"] == "Sir TestChar the Bold"
        assert data["quote"] == "Honor above all"
        assert data["description"] == "A stalwart knight"

    def test_can_apply_logic(self):
        """can_apply requires auth and available entry."""

        auth_user = type("User", (), {"is_authenticated": True})()
        anon_user = type("User", (), {"is_authenticated": False})()

        # Authenticated user, entry accepts applications
        data = self._serialize(auth_user)
        assert data["can_apply"]

        # Unauthenticated user
        data = self._serialize(anon_user)
        assert not data["can_apply"]

        # Entry no longer accepts applications
        RosterTenureFactory(roster_entry=self.entry)
        if hasattr(self.entry, "cached_tenures"):
            del self.entry.cached_tenures
        data = self._serialize(auth_user)
        assert not data["can_apply"]
