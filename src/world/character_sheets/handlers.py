"""
Data handlers for character sheet access.

Provides abstraction layer similar to Arx I's item_data handler system.
Allows property-based access like character.sheet_data.age instead of
having to use character.sheet_data_obj.age.
"""

from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from evennia.objects.objects import DefaultObject


class CharacterDataHandler:
    """
    Handler for character sheet data access.

    Provides property-based access to character sheet data similar to
    Arx I's item_data handler. Handles lazy loading and caching of
    related character data models.

    Usage:
        character.sheet_data.age  # Returns character's age
        character.sheet_data.eye_color  # Returns eye color characteristic
    """

    def __init__(self, character: "DefaultObject"):
        self.character = character
        self._sheet_cache = None
        self._display_data_cache = None
        self._characteristics_cache = None

    def _get_sheet(self):
        """Get or create the character sheet, with caching."""
        if self._sheet_cache is None:
            from world.character_sheets.models import CharacterSheet

            try:
                # Use the reverse relation, not the property
                self._sheet_cache = CharacterSheet.objects.get(character=self.character)
            except CharacterSheet.DoesNotExist:
                # Create a new sheet if one doesn't exist
                self._sheet_cache = CharacterSheet.objects.create(
                    character=self.character
                )
        return self._sheet_cache

    def _get_display_data(self):
        """Get or create the object display data, with caching."""
        if self._display_data_cache is None:
            from evennia_extensions.models import ObjectDisplayData

            try:
                # Use direct query, not the property
                self._display_data_cache = ObjectDisplayData.objects.get(
                    object=self.character
                )
            except ObjectDisplayData.DoesNotExist:
                # Create new display data if it doesn't exist
                self._display_data_cache = ObjectDisplayData.objects.create(
                    object=self.character
                )
        return self._display_data_cache

    def _get_characteristics(self):
        """Get character's characteristics as a dict, with caching."""
        if self._characteristics_cache is None:
            sheet = self._get_sheet()
            self._characteristics_cache = {}

            # Build a dictionary of characteristic_name: value
            for sheet_value in sheet.characteristic_values.select_related(
                "characteristic_value__characteristic"
            ):
                char_name = sheet_value.characteristic_value.characteristic.name
                char_value = sheet_value.characteristic_value.display_value
                self._characteristics_cache[char_name] = char_value

        return self._characteristics_cache

    def clear_cache(self):
        """Clear all cached data - call when data is updated."""
        self._sheet_cache = None
        self._display_data_cache = None
        self._characteristics_cache = None

    # Basic sheet data properties
    @property
    def age(self) -> int:
        return self._get_sheet().age

    @property
    def real_age(self) -> Optional[int]:
        return self._get_sheet().real_age

    @property
    def gender(self) -> str:
        return self._get_sheet().gender

    @property
    def concept(self) -> str:
        return self._get_sheet().concept

    @property
    def real_concept(self) -> str:
        return self._get_sheet().real_concept

    @property
    def marital_status(self) -> str:
        return self._get_sheet().marital_status

    @property
    def family(self) -> str:
        return self._get_sheet().family

    @property
    def vocation(self) -> str:
        return self._get_sheet().vocation

    @property
    def social_rank(self) -> int:
        return self._get_sheet().social_rank

    @property
    def birthday(self) -> str:
        return self._get_sheet().birthday

    @property
    def quote(self) -> str:
        return self._get_sheet().quote

    @property
    def personality(self) -> str:
        return self._get_sheet().personality

    @property
    def background(self) -> str:
        return self._get_sheet().background

    @property
    def obituary(self) -> str:
        return self._get_sheet().obituary

    @property
    def additional_desc(self) -> str:
        return self._get_sheet().additional_desc

    # Display data properties (from ObjectDisplayData)
    @property
    def longname(self) -> str:
        return self._get_display_data().longname

    @property
    def colored_name(self) -> str:
        return self._get_display_data().colored_name

    @property
    def permanent_description(self) -> str:
        return self._get_display_data().permanent_description

    @property
    def temporary_description(self) -> str:
        return self._get_display_data().temporary_description

    def get_display_name(self, include_colored: bool = True) -> str:
        """Get the appropriate display name for this character."""
        # Check for active guise first (false names), then fall back to ObjectDisplayData
        active_guise = self._get_active_guise()
        if active_guise:
            if include_colored and active_guise.colored_name:
                return active_guise.colored_name
            return active_guise.name

        # Fall back to ObjectDisplayData
        return self._get_display_data().get_display_name(include_colored)

    def get_display_description(self) -> str:
        """Get the appropriate description for this character."""
        # Check for active guise first, then fall back to ObjectDisplayData
        active_guise = self._get_active_guise()
        if active_guise and active_guise.description:
            return active_guise.description

        # Fall back to ObjectDisplayData
        return self._get_display_data().get_display_description()

    def _get_active_guise(self):
        """Get the currently active guise for this character, if any."""
        # For now, just return the default guise
        # Later this could be enhanced to support scene-specific guises
        from world.character_sheets.models import Guise

        try:
            return Guise.objects.get(character=self.character, is_default=True)
        except Guise.DoesNotExist:
            return None

    # Characteristic access
    def get_characteristic(self, name: str) -> Optional[str]:
        """Get a characteristic value by name."""
        characteristics = self._get_characteristics()
        return characteristics.get(name)

    @property
    def eye_color(self) -> Optional[str]:
        return self.get_characteristic("eye_color")

    @property
    def hair_color(self) -> Optional[str]:
        return self.get_characteristic("hair_color")

    @property
    def height(self) -> Optional[str]:
        return self.get_characteristic("height")

    @property
    def skin_tone(self) -> Optional[str]:
        return self.get_characteristic("skin_tone")

    # Setter methods for updating data
    def set_age(self, age: int):
        """Set character's age."""
        sheet = self._get_sheet()
        sheet.age = age
        sheet.save()

    def set_gender(self, gender: str):
        """Set character's gender."""
        sheet = self._get_sheet()
        sheet.gender = gender
        sheet.save()

    def set_concept(self, concept: str):
        """Set character's concept."""
        sheet = self._get_sheet()
        sheet.concept = concept
        sheet.save()

    def set_characteristic(self, characteristic_name: str, value: str):
        """Set a characteristic value for the character."""
        from world.character_sheets.models import (
            Characteristic,
            CharacteristicValue,
            CharacterSheetValue,
        )

        try:
            # Find the characteristic and value
            characteristic = Characteristic.objects.get(name=characteristic_name)
            char_value = CharacteristicValue.objects.get(
                characteristic=characteristic, value=value
            )

            sheet = self._get_sheet()

            # Remove any existing value for this characteristic
            CharacterSheetValue.objects.filter(
                character_sheet=sheet,
                characteristic_value__characteristic=characteristic,
            ).delete()

            # Set the new value
            CharacterSheetValue.objects.create(
                character_sheet=sheet, characteristic_value=char_value
            )

            # Clear cache so it gets reloaded
            self._characteristics_cache = None

        except (Characteristic.DoesNotExist, CharacteristicValue.DoesNotExist):
            raise ValueError(
                f"Invalid characteristic or value: {characteristic_name}={value}"
            )

    def __getattr__(self, name: str) -> Any:
        """
        Fallback for accessing any sheet attribute directly.
        This allows access to any field on the CharacterSheet model.
        """
        sheet = self._get_sheet()
        if hasattr(sheet, name):
            return getattr(sheet, name)
        raise AttributeError(
            f"'{self.__class__.__name__}' object has no attribute '{name}'"
        )


class CharacterItemDataHandler:
    """
    Unified flat interface for character data from multiple disparate sources.

    This handler provides descriptors that wrap different data storage objects
    and provides defaults from typeclasses when data objects aren't present.
    Maintains compatibility with Arx I's item_data system design.

    Data sources can include:
    - Character sheet data (demographics, social info)
    - Physical dimensions/weights (future)
    - Equipment data (future)
    - Other character-related storage systems
    """

    def __init__(self, character: "DefaultObject"):
        self.character = character
        self._sheet_handler = None
        # Future: self._physical_handler = None
        # Future: self._equipment_handler = None

    @property
    def _sheet_data(self):
        """Get the sheet data handler, lazy loaded."""
        if self._sheet_handler is None:
            self._sheet_handler = CharacterDataHandler(self.character)
        return self._sheet_handler

    # Sheet data properties - delegate to sheet handler
    @property
    def age(self) -> int:
        """Character's age from sheet data."""
        return self._sheet_data.age

    @property
    def gender(self) -> str:
        """Character's gender from sheet data."""
        return self._sheet_data.gender

    @property
    def concept(self) -> str:
        """Character's concept from sheet data."""
        return self._sheet_data.concept

    @property
    def family(self) -> str:
        """Character's family from sheet data."""
        return self._sheet_data.family

    @property
    def vocation(self) -> str:
        """Character's vocation from sheet data."""
        return self._sheet_data.vocation

    @property
    def social_rank(self) -> int:
        """Character's social rank from sheet data."""
        return self._sheet_data.social_rank

    @property
    def quote(self) -> str:
        """Character's quote from sheet data."""
        return self._sheet_data.quote

    @property
    def personality(self) -> str:
        """Character's personality from sheet data."""
        return self._sheet_data.personality

    @property
    def background(self) -> str:
        """Character's background from sheet data."""
        return self._sheet_data.background

    @property
    def longname(self) -> str:
        """Character's long name from description data."""
        return self._sheet_data.longname

    @property
    def colored_name(self) -> str:
        """Character's colored name from description data."""
        return self._sheet_data.colored_name

    # Physical characteristics from sheet data
    @property
    def eye_color(self) -> Optional[str]:
        """Character's eye color from characteristics."""
        return self._sheet_data.eye_color

    @property
    def hair_color(self) -> Optional[str]:
        """Character's hair color from characteristics."""
        return self._sheet_data.hair_color

    @property
    def height(self) -> Optional[str]:
        """Character's height category from characteristics."""
        return self._sheet_data.height

    @property
    def skin_tone(self) -> Optional[str]:
        """Character's skin tone from characteristics."""
        return self._sheet_data.skin_tone

    # Future: Physical dimensions (separate from height category)
    # @property
    # def height_inches(self) -> Optional[int]:
    #     """Character's exact height in inches from physical data."""
    #     # Would delegate to physical handler or return typeclass default
    #     return getattr(self.character, 'default_height_inches', None)
    #
    # @property
    # def weight_pounds(self) -> Optional[int]:
    #     """Character's weight in pounds from physical data."""
    #     # Would delegate to physical handler or return typeclass default
    #     return getattr(self.character, 'default_weight_pounds', None)

    def __getattr__(self, name: str) -> Any:
        """
        Fallback for accessing any attribute from underlying data sources.

        This provides the "flat interface" by checking multiple data sources
        in priority order, with fallbacks to typeclass defaults.
        """
        # Try sheet data first
        try:
            return getattr(self._sheet_data, name)
        except AttributeError:
            pass

        # Future: Try other data handlers
        # try:
        #     return getattr(self._physical_handler, name)
        # except AttributeError:
        #     pass

        # Fallback to typeclass defaults
        if hasattr(self.character, f"default_{name}"):
            return getattr(self.character, f"default_{name}")

        # If nothing found, raise AttributeError
        raise AttributeError(
            f"'{self.__class__.__name__}' object has no attribute '{name}'"
        )
