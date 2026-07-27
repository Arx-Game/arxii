"""
Tests for the unified item_data handler.

Tests the CharacterItemDataHandler's flat interface functionality.
"""

from django.test import TestCase
import pytest

from evennia_extensions.data_handlers import CharacterItemDataHandler
from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory, GenderFactory


class CharacterItemDataHandlerTests(TestCase):
    """Test CharacterItemDataHandler unified interface."""

    def setUp(self):
        """Set up test data."""
        self.character = CharacterFactory()
        self.handler = CharacterItemDataHandler(self.character)

    def test_flat_interface_access_to_sheet_data(self):
        """Test that item_data provides flat access to sheet data."""
        # Create sheet with test data
        gender = GenderFactory(key="female", display_name="Female")
        CharacterSheetFactory(
            character=self.character,
            matured_years=30,
            withered_years=0,
            gender=gender,
            concept="A test character",
        )

        # Should be accessible through flat interface (age = apparent age, #2756)
        assert self.handler.age == 30
        assert self.handler.gender == "Female"  # Returns display_name
        assert self.handler.concept == "A test character"

    def test_lazy_loading_of_sheet_handler(self):
        """Test that sheet handler is lazy loaded."""
        # Initially no handler should be loaded
        assert self.handler._sheet_handler is None

        # Accessing a property should load it
        _ = self.handler.age

        # Now handler should be loaded
        assert self.handler._sheet_handler is not None

    def test_birthday_renders_month_name_and_day(self):
        """The birthday property renders the celebrated month/day pair (#2756)."""
        CharacterSheetFactory(character=self.character, birthday_month=3, birthday_day=15)

        assert self.handler.birthday == "March 15"

    def test_attribute_error_when_no_source_found(self):
        """Test AttributeError when no data source has the attribute."""
        with pytest.raises(AttributeError):
            _ = self.handler.completely_nonexistent_attribute

    def test_integration_with_character_typeclass(self):
        """Test integration through character.item_data property."""
        CharacterSheetFactory(
            character=self.character,
            matured_years=25,
            withered_years=0,
            concept="Integration test",
        )

        # Should work through character.item_data
        assert self.character.item_data.age == 25
        assert self.character.item_data.concept == "Integration test"

        # Should be the same handler instance due to caching
        assert self.character.item_data is self.character.item_data
