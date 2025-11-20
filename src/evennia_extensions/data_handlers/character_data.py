"""
Comprehensive item data handler for Character objects.

This is the main data interface for characters, pulling from multiple sources:
- Character sheet data (demographics, descriptions)
- Classes app data (character classes, levels)
- Guise system (false names and disguises)
- Display data (longnames, colored names)
- Characteristics (eye color, height, etc.)
"""

from typing import TYPE_CHECKING

from evennia_extensions.data_handlers.base_data import BaseItemDataHandler

if TYPE_CHECKING:
    from evennia.objects.objects import DefaultObject


class CharacterItemDataHandler(BaseItemDataHandler):
    """
    Comprehensive item data handler for Character objects.

    This is the main data interface for characters, pulling from multiple sources:
    - Character sheet data (demographics, descriptions)
    - Classes app data (character classes, levels)
    - Progression app data (advancement, experience)
    - Guise system (false names and disguises)
    - Display data (longnames, colored names)
    - Characteristics (eye color, height, etc.)
    - Base object data (name, key, etc.)

    This replaces the need for a separate sheet_data handler.
    """

    def __init__(self, character: "DefaultObject"):
        super().__init__(character)
        self._sheet_cache = None
        self._display_data_cache = None
        self._characteristics_cache = None
        self._classes_cache = None
        self._guises_cache = None

    def _get_sheet(self):
        """Get or create the character sheet, with caching."""
        if self._sheet_cache is None:
            from world.character_sheets.models import CharacterSheet

            self._sheet_cache, _created = CharacterSheet.objects.get_or_create(
                character=self.obj,
            )
        return self._sheet_cache

    def _get_characteristics(self):
        """Get character characteristics data, with caching."""
        if self._characteristics_cache is None:
            from world.character_sheets.models import CharacterSheetValue

            # Build a dict of characteristic name -> display_value for easy access
            self._characteristics_cache = {}
            sheet = self._get_sheet()
            for csv in CharacterSheetValue.objects.filter(
                character_sheet=sheet,
            ).select_related("characteristic_value__characteristic"):
                char_name = csv.characteristic_value.characteristic.name.lower()
                display_value = csv.characteristic_value.display_value
                self._characteristics_cache[char_name] = display_value
        return self._characteristics_cache

    def _get_classes(self):
        """Get character class levels, with caching."""
        if self._classes_cache is None:
            from world.classes.models import CharacterClassLevel

            self._classes_cache = list(
                CharacterClassLevel.objects.filter(character=self.obj)
                .select_related("character_class")
                .order_by("-is_primary", "-level", "character_class__name"),
            )
        return self._classes_cache

    def _get_guises(self):
        """Get character guises, with caching."""
        if self._guises_cache is None:
            from world.character_sheets.models import Guise

            self._guises_cache = list(
                Guise.objects.filter(character=self.obj).order_by(
                    "-is_default", "name"
                ),
            )
        return self._guises_cache

    def _get_active_guise(self):
        """Get the currently active guise for this character."""
        guises = self._get_guises()
        # For now, return the default guise if any
        for guise in guises:
            if guise.is_default:
                return guise
        return None

    # Override base properties to return actual character data
    @property
    def age(self) -> int:
        """Character's age from sheet data."""
        sheet = self._get_sheet()
        return sheet.age

    @property
    def real_age(self) -> int:
        """Character's true age from sheet data (staff field)."""
        sheet = self._get_sheet()
        return sheet.real_age or sheet.age

    @property
    def gender(self) -> str:
        """Character's gender from sheet data."""
        sheet = self._get_sheet()
        return sheet.gender or ""

    @property
    def concept(self) -> str:
        """Character's concept from sheet data."""
        sheet = self._get_sheet()
        return sheet.concept or ""

    @property
    def real_concept(self) -> str:
        """Character's hidden concept from sheet data (staff field)."""
        sheet = self._get_sheet()
        return sheet.real_concept or ""

    @property
    def marital_status(self) -> str:
        """Character's marital status from sheet data."""
        sheet = self._get_sheet()
        return sheet.marital_status or "single"

    @property
    def family(self) -> str:
        """Character's family from sheet data."""
        sheet = self._get_sheet()
        return sheet.family or ""

    @property
    def vocation(self) -> str:
        """Character's vocation from sheet data."""
        sheet = self._get_sheet()
        return sheet.vocation or ""

    @property
    def social_rank(self) -> int:
        """Character's social rank from sheet data."""
        sheet = self._get_sheet()
        return sheet.social_rank

    @property
    def birthday(self) -> str:
        """Character's birthday from sheet data."""
        sheet = self._get_sheet()
        return sheet.birthday or ""

    @property
    def background(self) -> str:
        """Character's background from sheet data."""
        sheet = self._get_sheet()
        return sheet.background or ""

    @property
    def quote(self) -> str:
        """Character's quote from sheet data."""
        sheet = self._get_sheet()
        return sheet.quote or ""

    @property
    def personality(self) -> str:
        """Character's personality from sheet data."""
        sheet = self._get_sheet()
        return sheet.personality or ""

    @property
    def obituary(self) -> str:
        """Character's obituary if deceased (staff field)."""
        sheet = self._get_sheet()
        return sheet.obituary or ""

    @property
    def race(self):
        """Character's race from sheet data."""
        sheet = self._get_sheet()
        return sheet.race

    @property
    def subrace(self):
        """Character's subrace from sheet data."""
        sheet = self._get_sheet()
        return sheet.subrace

    @property
    def classes(self):
        """Character's class levels."""
        return self._get_classes()

    @property
    def guises(self):
        """Character's available guises."""
        return self._get_guises()

    def get_characteristic(self, name):
        """Get a characteristic value by name."""
        characteristics = self._get_characteristics()
        return characteristics.get(name.lower(), None)

    def set_characteristic(self, name, value):
        """Set a characteristic value by name."""
        from world.character_sheets.models import (
            Characteristic,
            CharacteristicValue,
            CharacterSheetValue,
        )

        sheet = self._get_sheet()

        # Only allow setting existing characteristics
        characteristic = Characteristic.objects.get(name=name.lower())

        # Get or create the characteristic value
        characteristic_value, _created = CharacteristicValue.objects.get_or_create(
            characteristic=characteristic,
            value=str(value).lower(),
            defaults={"display_value": str(value).replace("_", " ").title()},
        )

        # Remove any existing value for this characteristic
        CharacterSheetValue.objects.filter(
            character_sheet=sheet,
            characteristic_value__characteristic=characteristic,
        ).delete()

        # Create the new character sheet value
        CharacterSheetValue.objects.create(
            character_sheet=sheet,
            characteristic_value=characteristic_value,
        )

        # Clear the characteristics cache
        self._characteristics_cache = None

    def set_age(self, age):
        """Set the character's age."""
        sheet = self._get_sheet()
        sheet.age = age
        sheet.save()
        # Clear the sheet cache
        self._sheet_cache = None

    def clear_cache(self):
        """Clear all cached data, forcing fresh lookups."""
        self._sheet_cache = None
        self._display_data_cache = None
        self._characteristics_cache = None
        self._classes_cache = None
        self._guises_cache = None

    def get_primary_class(self):
        """Get the character's primary class."""
        classes = self._get_classes()
        for class_level in classes:
            if class_level.is_primary:
                return class_level
        return None

    def get_total_level(self):
        """Get the character's total level across all classes."""
        classes = self._get_classes()
        return sum(cl.level for cl in classes)

    def get_highest_level(self):
        """Get the character's highest single class level."""
        classes = self._get_classes()
        if not classes:
            return 0
        return max(cl.level for cl in classes)

    def get_class_by_name(self, class_name):
        """Get a specific class level by class name."""
        classes = self._get_classes()
        for class_level in classes:
            if class_level.character_class.name.lower() == class_name.lower():
                return class_level
        return None

    def get_guise_by_name(self, guise_name):
        """Get a specific guise by name."""
        guises = self._get_guises()
        for guise in guises:
            if guise.name.lower() == guise_name.lower():
                return guise
        return None

    def get_default_guise(self):
        """Get the character's default guise."""
        guises = self._get_guises()
        for guise in guises:
            if guise.is_default:
                return guise
        return None

    def get_display_name(self, include_colored=True):
        """
        Get the appropriate display name with guise override support.

        Args:
            include_colored (bool): Whether to include colored names

        Returns:
            str: The most appropriate display name (guise name if active,
                 otherwise display data)
        """
        # Check for active guise first
        active_guise = self.get_default_guise()
        if active_guise:
            if include_colored and active_guise.colored_name:
                return active_guise.colored_name
            return active_guise.name

        # Fall back to parent implementation (ObjectDisplayData)
        return super().get_display_name(include_colored=include_colored)

    def get_display_description(self):
        """Get character's current display description with guise override support."""
        # Check for active guise first
        active_guise = self.get_default_guise()
        if active_guise and active_guise.description:
            return active_guise.description

        # Fall back to parent implementation (ObjectDisplayData)
        return super().get_display_description()

    @property
    def _sheet_handler(self):
        """Legacy property for test compatibility - returns the sheet cache."""
        return self._sheet_cache

    # Explicit characteristic properties that the sheet command expects
    @property
    def eye_color(self) -> str:
        """Character's eye color characteristic."""
        return self.get_characteristic("eye_color") or ""

    @property
    def hair_color(self) -> str:
        """Character's hair color characteristic."""
        return self.get_characteristic("hair_color") or ""

    @property
    def height(self) -> str:
        """Character's height characteristic."""
        return self.get_characteristic("height") or ""

    @property
    def skin_tone(self) -> str:
        """Character's skin tone characteristic."""
        return self.get_characteristic("skin_tone") or ""

    # Additional sheet properties that may be accessed directly
    @property
    def additional_desc(self) -> str:
        """Character's additional description from sheet."""
        sheet = self._get_sheet()
        return sheet.additional_desc or ""
