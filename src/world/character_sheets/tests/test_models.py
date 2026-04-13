"""
Tests for character sheets models.

Tests focus on custom methods and behaviors, not standard Django functionality.
"""

from django.core.exceptions import ValidationError
from django.test import TestCase
import pytest

from world.character_sheets.factories import (
    CharacterFactory,
    CharacterIdentityFactory,
    CharacteristicFactory,
    CharacteristicValueFactory,
    CharacterSheetFactory,
    CharacterSheetValueFactory,
    CharacterWithCharacteristicsFactory,
    GenderFactory,
    ObjectDisplayDataFactory,
)
from world.character_sheets.identity_services import ensure_character_identity
from world.character_sheets.models import CharacterIdentity, CharacterSheet
from world.character_sheets.types import MaritalStatus


class CharacterSheetModelTests(TestCase):
    """Test CharacterSheet model custom functionality."""

    def setUp(self):
        """Set up test data."""
        # Flush SharedMemoryModel caches to prevent test pollution
        CharacterSheet.flush_instance_cache()
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)

    def test_character_sheet_creation(self):
        """Test creating a character sheet."""
        assert self.sheet.character == self.character
        assert self.sheet.age >= 18  # From factory validator
        # Gender is a nullable FK - factory creates without gender
        assert self.sheet.gender is None
        assert self.sheet.marital_status == MaritalStatus.SINGLE

    def test_character_sheet_with_gender(self):
        """Test creating a character sheet with gender FK."""
        gender = GenderFactory(key="male", display_name="Male")
        sheet = CharacterSheetFactory(character=CharacterFactory(), gender=gender)
        assert sheet.gender == gender
        assert sheet.gender.display_name == "Male"

    def test_character_sheet_str_representation(self):
        """Test string representation."""
        expected = f"Sheet for {self.character.db_key}"
        assert str(self.sheet) == expected

    def test_age_validation_constraints(self):
        """Test age validation works correctly."""
        # Test minimum age validation through model clean
        # Use a different character to avoid identity mapper returning the cached sheet
        new_char = CharacterFactory()
        sheet = CharacterSheet(character=new_char, age=15)
        with pytest.raises(ValidationError):
            sheet.full_clean()

    def test_social_rank_validation_constraints(self):
        """Test social rank validation works correctly."""
        # Test social rank bounds
        # Use a different character to avoid identity mapper returning the cached sheet
        new_char = CharacterFactory()
        sheet = CharacterSheet(character=new_char, social_rank=25)
        with pytest.raises(ValidationError):
            sheet.full_clean()


class ObjectDisplayDataModelTests(TestCase):
    """Test ObjectDisplayData model custom methods."""

    def setUp(self):
        """Set up test data."""
        self.character = CharacterFactory()
        self.display_data = ObjectDisplayDataFactory(
            object=self.character,
            longname="Sir TestChar the Bold",
            colored_name="|cTestChar|n",
            permanent_description="A tall warrior with piercing eyes.",
            temporary_description="Currently disguised as a merchant.",
        )

    def test_get_display_description_temporary_override(self):
        """Test that temporary description overrides permanent."""
        result = self.display_data.get_display_description()
        assert result == "Currently disguised as a merchant."

    def test_get_display_description_permanent_fallback(self):
        """Test fallback to permanent description."""
        self.display_data.temporary_description = ""
        result = self.display_data.get_display_description()
        assert result == "A tall warrior with piercing eyes."

    def test_get_display_description_empty_fallback(self):
        """Test behavior with no descriptions."""
        self.display_data.permanent_description = ""
        self.display_data.temporary_description = ""
        result = self.display_data.get_display_description()
        assert result == ""

    def test_get_display_name_colored_name_priority(self):
        """Test colored name has priority."""
        result = self.display_data.get_display_name(include_colored=True)
        assert result == "|cTestChar|n"

    def test_get_display_name_no_colored_flag(self):
        """Test skipping colored name when flag is False."""
        result = self.display_data.get_display_name(include_colored=False)
        assert result == "Sir TestChar the Bold"

    def test_get_display_name_longname_fallback(self):
        """Test longname fallback."""
        self.display_data.colored_name = ""
        result = self.display_data.get_display_name()
        assert result == "Sir TestChar the Bold"

    def test_get_display_name_character_key_final_fallback(self):
        """Test final fallback to object key."""
        self.display_data.colored_name = ""
        self.display_data.longname = ""
        result = self.display_data.get_display_name()
        assert result == self.character.db_key


class CharacteristicModelTests(TestCase):
    """Test Characteristic and related models."""

    def test_characteristic_value_display_value_default(self):
        """Test that display_value defaults to value when not provided."""
        characteristic = CharacteristicFactory(name="test_eye_color")
        char_value = CharacteristicValueFactory(
            characteristic=characteristic,
            value="dark_blue",
        )

        # display_value should be set automatically
        assert char_value.display_value == "Dark Blue"

    def test_characteristic_value_str_representation(self):
        """Test string representation."""
        characteristic = CharacteristicFactory(
            name="test_eye_color_2",
            display_name="Test Eye Color",
        )
        char_value = CharacteristicValueFactory(
            characteristic=characteristic,
            value="blue",
            display_value="Bright Blue",
        )

        expected = "Test Eye Color: Bright Blue"
        assert str(char_value) == expected

    def test_characteristic_str_representation(self):
        """Test characteristic string representation."""
        characteristic = CharacteristicFactory(display_name="Eye Color")
        assert str(characteristic) == "Eye Color"


class CharacterSheetValueModelTests(TestCase):
    """Test CharacterSheetValue linking model."""

    def test_character_sheet_value_str_representation(self):
        """Test string representation."""
        data = CharacterWithCharacteristicsFactory.create(
            characteristics={"eye_color": "blue"},
        )
        sheet_value = data["characteristic_values"][0]

        expected = f"{data['character'].db_key}: Eye Color: Blue"
        assert str(sheet_value) == expected

    def test_unique_character_characteristic_constraint(self):
        """Test that a character can only have one value per characteristic."""
        characteristic = CharacteristicFactory(name="test_unique_constraint")
        blue_value = CharacteristicValueFactory(
            characteristic=characteristic,
            value="blue",
        )
        green_value = CharacteristicValueFactory(
            characteristic=characteristic,
            value="green",
        )

        sheet = CharacterSheetFactory()

        # First assignment should work
        CharacterSheetValueFactory(
            character_sheet=sheet,
            characteristic_value=blue_value,
        )

        # Second assignment to same characteristic should fail
        from django.core.exceptions import ValidationError

        with pytest.raises(ValidationError):
            CharacterSheetValueFactory(
                character_sheet=sheet,
                characteristic_value=green_value,
            )


class CharacterSheetPronounTests(TestCase):
    """Test pronoun fields on CharacterSheet."""

    def test_pronoun_fields_exist(self):
        """Test CharacterSheet has pronoun fields with defaults."""
        character = CharacterFactory()
        sheet = CharacterSheetFactory(character=character)

        assert sheet.pronoun_subject == "they"
        assert sheet.pronoun_object == "them"
        assert sheet.pronoun_possessive == "their"

    def test_pronoun_fields_settable(self):
        """Test pronoun fields can be set to custom values."""
        character = CharacterFactory()
        sheet = CharacterSheetFactory(
            character=character,
            pronoun_subject="he",
            pronoun_object="him",
            pronoun_possessive="his",
        )
        assert sheet.pronoun_subject == "he"
        assert sheet.pronoun_object == "him"
        assert sheet.pronoun_possessive == "his"


class CharacterIdentityModelTests(TestCase):
    """Test CharacterIdentity model."""

    def test_character_identity_creation(self):
        """Test creating a CharacterIdentity with all FK fields."""
        identity = CharacterIdentityFactory()
        assert identity.character is not None
        assert identity.active_persona is not None
        assert identity.active_persona.character_identity == identity
        assert identity.active_persona is not None

    def test_onetoone_constraint(self):
        """Test that a character can only have one CharacterIdentity."""
        from django.db import IntegrityError

        identity = CharacterIdentityFactory()
        with pytest.raises(IntegrityError):
            CharacterIdentityFactory(character=identity.character)

    def test_str_representation(self):
        """Test string representation."""
        identity = CharacterIdentityFactory()
        expected = f"Identity: {identity.active_persona.name} ({identity.character.db_key})"
        assert str(identity) == expected


class EnsureCharacterIdentityTests(TestCase):
    """Test ensure_character_identity service function."""

    def test_creates_from_scratch(self):
        """Test creating identity and primary persona from scratch."""
        character = CharacterFactory()
        identity = ensure_character_identity(character)

        assert identity.character == character
        assert identity.active_persona is not None
        assert identity.active_persona.name == character.db_key
        assert identity.active_persona.character == character
        assert identity.active_persona.character_identity == identity
        assert identity.active_persona.is_fake_name is False

    def test_idempotent(self):
        """Test calling ensure_character_identity twice returns same identity."""
        character = CharacterFactory()
        identity1 = ensure_character_identity(character)
        identity2 = ensure_character_identity(character)

        assert identity1.pk == identity2.pk
        assert CharacterIdentity.objects.filter(character=character).count() == 1
        assert identity1.active_persona is not None

    def test_idempotent_returns_existing(self):
        """Test that existing identity is returned."""
        character = CharacterFactory()
        identity1 = ensure_character_identity(character)
        identity2 = ensure_character_identity(character)
        assert identity1.pk == identity2.pk


class CharacterSheetPrimaryPersonaTest(TestCase):
    def test_primary_persona_returns_primary_when_exists(self) -> None:
        from world.scenes.constants import PersonaType
        from world.scenes.models import Persona

        # Build a character with an identity + sheet pointing at the same character
        identity = CharacterIdentityFactory()
        character = identity.character
        sheet = CharacterSheetFactory(character=character)
        # The identity factory already created a PRIMARY persona; link it to the sheet
        primary = identity.active_persona
        primary.character_sheet = sheet
        primary.save(update_fields=["character_sheet"])
        # Add an ESTABLISHED persona linked to the same sheet
        Persona.objects.create(
            character_identity=identity,
            character=character,
            character_sheet=sheet,
            name="Alter Ego",
            persona_type=PersonaType.ESTABLISHED,
        )
        assert sheet.primary_persona == primary

    def test_primary_persona_raises_when_no_primary(self) -> None:
        from world.scenes.models import Persona

        sheet = CharacterSheetFactory()
        with self.assertRaises(Persona.DoesNotExist):
            _ = sheet.primary_persona


class CharacterSheetDisplayDelegatesTest(TestCase):
    """Tests that CharacterSheet.display_* delegate to primary_persona."""

    def test_display_ic_delegates_to_primary_persona(self) -> None:
        from world.character_sheets.factories import (
            CharacterIdentityFactory,
            CharacterSheetFactory,
        )

        sheet = CharacterSheetFactory()
        identity = CharacterIdentityFactory(character=sheet.character)
        primary = identity.active_persona
        primary.character_sheet = sheet
        primary.name = "Bob"
        primary.save()
        assert sheet.display_ic() == "Bob"

    def test_display_with_history_delegates(self) -> None:
        from world.character_sheets.factories import (
            CharacterIdentityFactory,
            CharacterSheetFactory,
        )

        sheet = CharacterSheetFactory()
        identity = CharacterIdentityFactory(character=sheet.character)
        primary = identity.active_persona
        primary.character_sheet = sheet
        primary.name = "Alice"
        primary.save()
        # No tenure, so result is just the name
        assert sheet.display_with_history() == "Alice"

    def test_display_to_staff_delegates(self) -> None:
        from world.character_sheets.factories import (
            CharacterIdentityFactory,
            CharacterSheetFactory,
        )

        sheet = CharacterSheetFactory()
        identity = CharacterIdentityFactory(character=sheet.character)
        primary = identity.active_persona
        primary.character_sheet = sheet
        primary.name = "Charlie"
        primary.save()
        # No roster_entry → name only
        assert sheet.display_to_staff() == "Charlie"


class CharacterIdentityFactoryTests(TestCase):
    """Test CharacterIdentityFactory."""

    def test_factory_creates_valid_instance(self):
        """Test that the factory creates a valid CharacterIdentity."""
        identity = CharacterIdentityFactory()
        assert identity.pk is not None
        assert identity.active_persona.character == identity.character
        assert identity.active_persona.character_identity == identity
