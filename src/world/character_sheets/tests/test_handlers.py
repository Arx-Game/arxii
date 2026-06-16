"""
Tests for character data handlers.

Tests the CharacterDataHandler's custom methods and caching behavior.
"""

from django.test import TestCase
import pytest

from evennia_extensions.data_handlers import (
    CharacterItemDataHandler as CharacterDataHandler,
)
from evennia_extensions.models import ObjectDisplayData
from world.character_sheets.factories import (
    CharacterFactory,
    CharacterSheetFactory,
    CharacterWithCharacteristicsFactory,
    GenderFactory,
    ObjectDisplayDataFactory,
)
from world.character_sheets.models import CharacterSheet


class CharacterDataHandlerTests(TestCase):
    """Test CharacterDataHandler functionality."""

    def setUp(self):
        """Set up test data."""
        self.character = CharacterFactory()
        self.handler = CharacterDataHandler(self.character)

    def test_handler_creates_sheet_if_missing(self):
        """Test that handler creates CharacterSheet if it doesn't exist."""
        # Ensure no sheet exists
        assert not CharacterSheet.objects.filter(character=self.character).exists()

        # Accessing age should create the sheet
        age = self.handler.age

        # Sheet should now exist with default age
        assert CharacterSheet.objects.filter(character=self.character).exists()
        assert age == 18  # Default age from model

    def test_handler_creates_display_data_if_missing(self):
        """Test that handler creates ObjectDisplayData if it doesn't exist."""
        # Ensure no display data exists
        assert not ObjectDisplayData.objects.filter(object=self.character).exists()

        # Accessing longname should create the display data
        longname = self.handler.longname

        # Display data should now exist
        assert ObjectDisplayData.objects.filter(object=self.character).exists()
        assert longname == ""  # Default empty longname

    def test_handler_caches_sheet_data(self):
        """Test that sheet data is cached after first access."""
        # Create sheet manually
        CharacterSheetFactory(character=self.character, age=25)

        # First access
        age1 = self.handler.age

        # Modify sheet directly in database, bypassing identity mapper
        CharacterSheet.objects.filter(character=self.character).update(age=30)

        # Second access should return cached value (handler holds reference to
        # the identity-mapped instance, which was not updated by .update())
        age2 = self.handler.age

        assert age1 == 25
        assert age2 == 25  # Still cached

    def test_clear_cache_refreshes_data(self):
        """Test that clearing cache refreshes data."""
        # Create sheet
        CharacterSheetFactory(character=self.character, age=25)

        # First access (caches data)
        age1 = self.handler.age

        # Modify sheet directly in DB, bypassing identity mapper
        CharacterSheet.objects.filter(character=self.character).update(age=30)
        # Flush identity mapper so the handler re-fetches fresh data
        CharacterSheet.flush_instance_cache()

        # Clear handler cache
        self.handler.clear_cache()

        # Access should now return updated value
        age2 = self.handler.age

        assert age1 == 25
        assert age2 == 30

    def test_basic_sheet_property_access(self):
        """Test basic property access works correctly."""
        gender = GenderFactory(key="female", display_name="Female")
        CharacterSheetFactory(
            character=self.character,
            age=25,
            gender=gender,
            concept="A brave warrior",
            social_rank=5,
        )

        assert self.handler.age == 25
        assert self.handler.gender == "Female"  # Returns display_name
        assert self.handler.concept == "A brave warrior"
        assert self.handler.social_rank == 5

    def test_display_data_property_access(self):
        """Test display data property access works correctly."""
        ObjectDisplayDataFactory(
            object=self.character,
            longname="Sir TestChar",
            colored_name="|cTestChar|n",
            permanent_description="A noble warrior",
        )

        assert self.handler.longname == "Sir TestChar"
        assert self.handler.colored_name == "|cTestChar|n"
        assert self.handler.permanent_description == "A noble warrior"

    def test_characteristic_access(self):
        """item_data exposes appearance traits (FormTrait-backed, descriptor-aware)."""
        data = CharacterWithCharacteristicsFactory.create(
            characteristics={"eye_color": "blue", "hair_color": "brown"},
        )

        handler = CharacterDataHandler(data["character"])

        assert handler.eye_color == "Blue"
        assert handler.hair_color == "Brown"

    def test_skin_tone_reflects_descriptor(self):
        """A persona descriptor overrides the normalized value in item_data."""
        from world.forms.factories import PersonaTraitDescriptorFactory
        from world.forms.models import FormTrait

        data = CharacterWithCharacteristicsFactory.create(
            characteristics={"skin_tone": "fair"},
        )
        character = data["character"]
        skin_trait = FormTrait.objects.get(name="skin_tone")
        PersonaTraitDescriptorFactory(
            persona=character.sheet_data.primary_persona,
            trait=skin_trait,
            text="Porcelain",
        )

        handler = CharacterDataHandler(character)

        assert handler.skin_tone == "Porcelain"

    def test_set_age_method(self):
        """Test setting age updates database."""
        self.handler.set_age(30)

        # Should be reflected in fresh handler
        new_handler = CharacterDataHandler(self.character)
        assert new_handler.age == 30

    def test_display_name_methods(self):
        """Test display name helper methods."""
        # Create display data
        ObjectDisplayDataFactory(
            object=self.character,
            longname="Sir TestChar",
            permanent_description="A warrior",
            temporary_description="Disguised as merchant",
        )

        # Create identity with primary persona
        CharacterSheetFactory(character=self.character)

        # Test display name (should use primary persona name = character db_key)
        display_name = self.handler.get_display_name()
        assert display_name == self.character.db_key

        # Test display description (persona has no description, falls back to display data)
        display_desc = self.handler.get_display_description()
        assert display_desc == "Disguised as merchant"

    def test_getattr_fallback(self):
        """Test __getattr__ fallback for direct sheet access."""
        CharacterSheetFactory(
            character=self.character,
            additional_desc="Extra description",
        )

        # Should be able to access any sheet field directly
        assert self.handler.additional_desc == "Extra description"

        # Should raise AttributeError for non-existent attributes
        with pytest.raises(AttributeError):
            _ = self.handler.nonexistent_attribute
