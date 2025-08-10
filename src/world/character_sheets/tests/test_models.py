"""
Tests for character sheets models.

Tests focus on custom methods and behaviors, not standard Django functionality.
"""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.character_sheets.factories import (
    CharacterFactory,
    CharacteristicFactory,
    CharacteristicValueFactory,
    CharacterSheetFactory,
    CharacterSheetValueFactory,
    CharacterWithCharacteristicsFactory,
    GuiseFactory,
    ObjectDisplayDataFactory,
)
from world.character_sheets.models import CharacterSheet
from world.character_sheets.types import Gender, MaritalStatus


class CharacterSheetModelTests(TestCase):
    """Test CharacterSheet model custom functionality."""

    def setUp(self):
        """Set up test data."""
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)

    def test_character_sheet_creation(self):
        """Test creating a character sheet."""
        self.assertEqual(self.sheet.character, self.character)
        self.assertGreaterEqual(self.sheet.age, 18)  # From factory validator
        self.assertIn(self.sheet.gender, [choice[0] for choice in Gender.choices])
        self.assertEqual(self.sheet.marital_status, MaritalStatus.SINGLE)

    def test_character_sheet_str_representation(self):
        """Test string representation."""
        expected = f"Sheet for {self.character.db_key}"
        self.assertEqual(str(self.sheet), expected)

    def test_age_validation_constraints(self):
        """Test age validation works correctly."""
        # Test minimum age validation through model clean
        sheet = CharacterSheet(character=self.character, age=15)
        with self.assertRaises(ValidationError):
            sheet.full_clean()

    def test_social_rank_validation_constraints(self):
        """Test social rank validation works correctly."""
        # Test social rank bounds
        sheet = CharacterSheet(character=self.character, social_rank=25)
        with self.assertRaises(ValidationError):
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
        self.assertEqual(result, "Currently disguised as a merchant.")

    def test_get_display_description_permanent_fallback(self):
        """Test fallback to permanent description."""
        self.display_data.temporary_description = ""
        result = self.display_data.get_display_description()
        self.assertEqual(result, "A tall warrior with piercing eyes.")

    def test_get_display_description_empty_fallback(self):
        """Test behavior with no descriptions."""
        self.display_data.permanent_description = ""
        self.display_data.temporary_description = ""
        result = self.display_data.get_display_description()
        self.assertEqual(result, "")

    def test_get_display_name_colored_name_priority(self):
        """Test colored name has priority."""
        result = self.display_data.get_display_name(include_colored=True)
        self.assertEqual(result, "|cTestChar|n")

    def test_get_display_name_no_colored_flag(self):
        """Test skipping colored name when flag is False."""
        result = self.display_data.get_display_name(include_colored=False)
        self.assertEqual(result, "Sir TestChar the Bold")

    def test_get_display_name_longname_fallback(self):
        """Test longname fallback."""
        self.display_data.colored_name = ""
        result = self.display_data.get_display_name()
        self.assertEqual(result, "Sir TestChar the Bold")

    def test_get_display_name_character_key_final_fallback(self):
        """Test final fallback to object key."""
        self.display_data.colored_name = ""
        self.display_data.longname = ""
        result = self.display_data.get_display_name()
        self.assertEqual(result, self.character.db_key)


class GuiseModelTests(TestCase):
    """Test Guise model custom functionality."""

    def setUp(self):
        """Set up test data."""
        self.character = CharacterFactory()

    def test_only_one_default_guise_per_character(self):
        """Test that setting a guise as default clears other defaults."""
        # Create first default guise
        guise1 = GuiseFactory(character=self.character, is_default=True, name="First")

        # Create second default guise
        guise2 = GuiseFactory(character=self.character, is_default=True, name="Second")

        # Refresh from database
        guise1.refresh_from_db()

        # First guise should no longer be default
        self.assertFalse(guise1.is_default)
        self.assertTrue(guise2.is_default)

    def test_multiple_non_default_guises_allowed(self):
        """Test that multiple non-default guises are allowed."""
        guise1 = GuiseFactory(character=self.character, is_default=False, name="First")
        guise2 = GuiseFactory(character=self.character, is_default=False, name="Second")

        # Both should remain non-default
        self.assertFalse(guise1.is_default)
        self.assertFalse(guise2.is_default)

    def test_guise_str_representation(self):
        """Test string representation includes default status."""
        guise = GuiseFactory(
            character=self.character, is_default=True, name="TestGuise"
        )
        expected = f"TestGuise for {self.character.db_key} (default)"
        self.assertEqual(str(guise), expected)

    def test_guise_str_representation_non_default(self):
        """Test string representation for non-default guise."""
        guise = GuiseFactory(
            character=self.character, is_default=False, name="TestGuise"
        )
        expected = f"TestGuise for {self.character.db_key}"
        self.assertEqual(str(guise), expected)

    def test_guise_colored_name_field(self):
        """Test that colored_name field is properly stored and retrieved."""
        guise = GuiseFactory(
            character=self.character, name="TestGuise", colored_name="|rTestGuise|n"
        )
        self.assertEqual(guise.colored_name, "|rTestGuise|n")

    def test_unique_character_name_constraint(self):
        """Test that character + name must be unique."""
        GuiseFactory(character=self.character, name="TestGuise")

        # Creating another guise with same name should fail
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            GuiseFactory(character=self.character, name="TestGuise")


class CharacteristicModelTests(TestCase):
    """Test Characteristic and related models."""

    def test_characteristic_value_display_value_default(self):
        """Test that display_value defaults to value when not provided."""
        characteristic = CharacteristicFactory(name="test_eye_color")
        char_value = CharacteristicValueFactory(
            characteristic=characteristic, value="dark_blue"
        )

        # display_value should be set automatically
        self.assertEqual(char_value.display_value, "Dark Blue")

    def test_characteristic_value_str_representation(self):
        """Test string representation."""
        characteristic = CharacteristicFactory(
            name="test_eye_color_2", display_name="Test Eye Color"
        )
        char_value = CharacteristicValueFactory(
            characteristic=characteristic, value="blue", display_value="Bright Blue"
        )

        expected = "Test Eye Color: Bright Blue"
        self.assertEqual(str(char_value), expected)

    def test_characteristic_str_representation(self):
        """Test characteristic string representation."""
        characteristic = CharacteristicFactory(display_name="Eye Color")
        self.assertEqual(str(characteristic), "Eye Color")


class CharacterSheetValueModelTests(TestCase):
    """Test CharacterSheetValue linking model."""

    def test_character_sheet_value_str_representation(self):
        """Test string representation."""
        data = CharacterWithCharacteristicsFactory.create(
            characteristics={"eye_color": "blue"}
        )
        sheet_value = data["characteristic_values"][0]

        expected = f"{data['character'].db_key}: Eye Color: Blue"
        self.assertEqual(str(sheet_value), expected)

    def test_unique_character_characteristic_constraint(self):
        """Test that a character can only have one value per characteristic."""
        characteristic = CharacteristicFactory(name="test_unique_constraint")
        blue_value = CharacteristicValueFactory(
            characteristic=characteristic, value="blue"
        )
        green_value = CharacteristicValueFactory(
            characteristic=characteristic, value="green"
        )

        sheet = CharacterSheetFactory()

        # First assignment should work
        CharacterSheetValueFactory(
            character_sheet=sheet, characteristic_value=blue_value
        )

        # Second assignment to same characteristic should fail
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            CharacterSheetValueFactory(
                character_sheet=sheet, characteristic_value=green_value
            )
