"""
Tests for character data handlers.

Tests the CharacterDataHandler's custom methods and caching behavior.
"""

from django.core.exceptions import ObjectDoesNotExist
from django.test import TestCase

from evennia_extensions.data_handlers import (
    CharacterItemDataHandler as CharacterDataHandler,
)
from evennia_extensions.models import ObjectDisplayData
from world.character_sheets.factories import (
    BasicCharacteristicsSetupFactory,
    CharacterFactory,
    CharacterSheetFactory,
    CharacterWithCharacteristicsFactory,
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
        self.assertFalse(
            CharacterSheet.objects.filter(character=self.character).exists()
        )

        # Accessing age should create the sheet
        age = self.handler.age

        # Sheet should now exist with default age
        self.assertTrue(
            CharacterSheet.objects.filter(character=self.character).exists()
        )
        self.assertEqual(age, 18)  # Default age from model

    def test_handler_creates_display_data_if_missing(self):
        """Test that handler creates ObjectDisplayData if it doesn't exist."""
        # Ensure no display data exists
        self.assertFalse(
            ObjectDisplayData.objects.filter(object=self.character).exists()
        )

        # Accessing longname should create the display data
        longname = self.handler.longname

        # Display data should now exist
        self.assertTrue(
            ObjectDisplayData.objects.filter(object=self.character).exists()
        )
        self.assertEqual(longname, "")  # Default empty longname

    def test_handler_caches_sheet_data(self):
        """Test that sheet data is cached after first access."""
        # Create sheet manually
        sheet = CharacterSheetFactory(character=self.character, age=25)

        # First access
        age1 = self.handler.age

        # Modify sheet directly in database
        sheet.age = 30
        sheet.save()

        # Second access should return cached value
        age2 = self.handler.age

        self.assertEqual(age1, 25)
        self.assertEqual(age2, 25)  # Still cached

    def test_clear_cache_refreshes_data(self):
        """Test that clearing cache refreshes data."""
        # Create sheet
        sheet = CharacterSheetFactory(character=self.character, age=25)

        # First access (caches data)
        age1 = self.handler.age

        # Modify sheet
        sheet.age = 30
        sheet.save()

        # Clear cache
        self.handler.clear_cache()

        # Access should now return updated value
        age2 = self.handler.age

        self.assertEqual(age1, 25)
        self.assertEqual(age2, 30)

    def test_basic_sheet_property_access(self):
        """Test basic property access works correctly."""
        CharacterSheetFactory(
            character=self.character,
            age=25,
            gender="female",
            concept="A brave warrior",
            social_rank=5,
        )

        self.assertEqual(self.handler.age, 25)
        self.assertEqual(self.handler.gender, "female")
        self.assertEqual(self.handler.concept, "A brave warrior")
        self.assertEqual(self.handler.social_rank, 5)

    def test_display_data_property_access(self):
        """Test display data property access works correctly."""
        ObjectDisplayDataFactory(
            object=self.character,
            longname="Sir TestChar",
            colored_name="|cTestChar|n",
            permanent_description="A noble warrior",
        )

        self.assertEqual(self.handler.longname, "Sir TestChar")
        self.assertEqual(self.handler.colored_name, "|cTestChar|n")
        self.assertEqual(self.handler.permanent_description, "A noble warrior")

    def test_characteristic_access(self):
        """Test characteristic value access."""
        # Create basic characteristics setup
        BasicCharacteristicsSetupFactory.create()

        # Create character with characteristics
        data = CharacterWithCharacteristicsFactory.create(
            characteristics={"eye_color": "blue", "hair_color": "brown"}
        )

        handler = CharacterDataHandler(data["character"])

        self.assertEqual(handler.eye_color, "Blue")
        self.assertEqual(handler.hair_color, "Brown")

    def test_get_characteristic_method(self):
        """Test generic characteristic getter."""
        # Create basic characteristics
        BasicCharacteristicsSetupFactory.create()

        # Create character with characteristics
        data = CharacterWithCharacteristicsFactory.create(
            characteristics={"height": "tall", "skin_tone": "fair"}
        )

        handler = CharacterDataHandler(data["character"])

        self.assertEqual(handler.get_characteristic("height"), "Tall")
        self.assertEqual(handler.get_characteristic("skin_tone"), "Fair")
        self.assertIsNone(handler.get_characteristic("nonexistent"))

    def test_characteristic_caching(self):
        """Test that characteristics are cached properly."""
        # Create characteristics
        BasicCharacteristicsSetupFactory.create()
        data = CharacterWithCharacteristicsFactory.create(
            characteristics={"eye_color": "blue"}
        )

        handler = CharacterDataHandler(data["character"])

        # First access (should cache)
        color1 = handler.eye_color

        # Modify characteristic directly
        sheet_value = data["characteristic_values"][0]
        from world.character_sheets.models import CharacteristicValue

        new_value = CharacteristicValue.objects.get(value="green")
        sheet_value.characteristic_value = new_value
        sheet_value.save()

        # Second access should still be cached
        color2 = handler.eye_color

        self.assertEqual(color1, "Blue")
        self.assertEqual(color2, "Blue")  # Still cached

    def test_set_age_method(self):
        """Test setting age updates database."""
        self.handler.set_age(30)

        # Should be reflected in fresh handler
        new_handler = CharacterDataHandler(self.character)
        self.assertEqual(new_handler.age, 30)

    def test_set_characteristic_method(self):
        """Test setting characteristic values."""
        # Create basic characteristics
        BasicCharacteristicsSetupFactory.create()

        handler = CharacterDataHandler(self.character)
        handler.set_characteristic("eye_color", "blue")

        # Should be accessible
        self.assertEqual(handler.eye_color, "Blue")

        # Should persist to new handler
        new_handler = CharacterDataHandler(self.character)
        self.assertEqual(new_handler.eye_color, "Blue")

    def test_set_characteristic_replaces_existing(self):
        """Test that setting characteristic replaces existing value."""
        # Create basic characteristics
        BasicCharacteristicsSetupFactory.create()

        handler = CharacterDataHandler(self.character)
        handler.set_characteristic("eye_color", "blue")
        self.assertEqual(handler.eye_color, "Blue")

        # Change to different value
        handler.set_characteristic("eye_color", "green")

        # Should reflect new value (after cache clear)
        new_handler = CharacterDataHandler(self.character)
        self.assertEqual(new_handler.eye_color, "Green")

    def test_set_characteristic_invalid_raises_error(self):
        """Test that invalid characteristic/value combinations raise errors."""
        with self.assertRaises(ObjectDoesNotExist):
            self.handler.set_characteristic("nonexistent", "value")

    def test_display_name_methods(self):
        """Test display name helper methods."""
        from world.character_sheets.models import Guise

        # Create display data
        ObjectDisplayDataFactory(
            object=self.character,
            longname="Sir TestChar",
            permanent_description="A warrior",
            temporary_description="Disguised as merchant",
        )

        # Create a guise (false name)
        Guise.objects.create(
            character=self.character,
            name="Mysterious Stranger",
            description="A hooded figure",
            is_default=True,
        )

        # Test display name (should use guise name)
        display_name = self.handler.get_display_name()
        self.assertEqual(display_name, "Mysterious Stranger")

        # Test display description (should use guise description)
        display_desc = self.handler.get_display_description()
        self.assertEqual(display_desc, "A hooded figure")

    def test_getattr_fallback(self):
        """Test __getattr__ fallback for direct sheet access."""
        CharacterSheetFactory(
            character=self.character, additional_desc="Extra description"
        )

        # Should be able to access any sheet field directly
        self.assertEqual(self.handler.additional_desc, "Extra description")

        # Should raise AttributeError for non-existent attributes
        with self.assertRaises(AttributeError):
            _ = self.handler.nonexistent_attribute
