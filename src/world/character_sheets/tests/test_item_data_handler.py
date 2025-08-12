"""
Tests for the unified item_data handler.

Tests the CharacterItemDataHandler's flat interface functionality.
"""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.handlers import CharacterItemDataHandler


class CharacterItemDataHandlerTests(TestCase):
    """Test CharacterItemDataHandler unified interface."""

    def setUp(self):
        """Set up test data."""
        self.character = CharacterFactory()
        self.handler = CharacterItemDataHandler(self.character)

    def test_flat_interface_access_to_sheet_data(self):
        """Test that item_data provides flat access to sheet data."""
        # Create sheet with test data
        CharacterSheetFactory(
            character=self.character,
            age=30,
            gender="female",
            concept="A test character",
        )

        # Should be accessible through flat interface
        self.assertEqual(self.handler.age, 30)
        self.assertEqual(self.handler.gender, "female")
        self.assertEqual(self.handler.concept, "A test character")

    def test_lazy_loading_of_sheet_handler(self):
        """Test that sheet handler is lazy loaded."""
        # Initially no handler should be loaded
        self.assertIsNone(self.handler._sheet_handler)

        # Accessing a property should load it
        _ = self.handler.age

        # Now handler should be loaded
        self.assertIsNotNone(self.handler._sheet_handler)

    def test_fallback_to_getattr_for_unmapped_attributes(self):
        """Test fallback to __getattr__ for attributes not explicitly mapped."""
        CharacterSheetFactory(character=self.character, birthday="Spring 15th")

        # birthday is not explicitly mapped as a property
        # but should be accessible through __getattr__
        self.assertEqual(self.handler.birthday, "Spring 15th")

    def test_typeclass_default_fallback(self):
        """Test fallback to typeclass defaults when data not available."""
        # Add a default to the character typeclass
        self.character.default_test_value = "default_from_typeclass"

        # Should return the default value
        self.assertEqual(self.handler.test_value, "default_from_typeclass")

    def test_attribute_error_when_no_source_found(self):
        """Test AttributeError when no data source has the attribute."""
        with self.assertRaises(AttributeError):
            _ = self.handler.completely_nonexistent_attribute

    def test_integration_with_character_typeclass(self):
        """Test integration through character.item_data property."""
        CharacterSheetFactory(
            character=self.character, age=25, concept="Integration test"
        )

        # Should work through character.item_data
        self.assertEqual(self.character.item_data.age, 25)
        self.assertEqual(self.character.item_data.concept, "Integration test")

        # Should be the same handler instance due to caching
        self.assertIs(self.character.item_data, self.character.item_data)
