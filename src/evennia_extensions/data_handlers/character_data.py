"""
Comprehensive item data handler for Character objects.

This is the main data interface for characters, pulling from multiple sources:
- Character sheet data (demographics, descriptions)
- Classes app data (character classes, levels)
- Persona system (identities and disguises)
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
    - Persona system (identities and disguises)
    - Display data (longnames, colored names)
    - Characteristics (eye color, height, etc.)
    - Base object data (name, key, etc.)

    This replaces the need for a separate sheet_data handler.
    """

    def __init__(self, character: "DefaultObject"):
        super().__init__(character)
        self._sheet_cache = None
        self._display_data_cache = None
        self._presented_appearance_cache = None
        self._classes_cache = None
        self._personas_cache = None

    def _get_sheet(self):
        """Get or create the character sheet, with caching.

        Pulls ``true_profile`` in the same query (#1270) so bio reads (concept/quote/
        background, exposed as forwarding properties) don't add a per-character query.
        """
        if self._sheet_cache is None:
            from world.character_sheets.models import CharacterSheet

            self._sheet_cache, _created = CharacterSheet.objects.select_related(
                "true_profile"
            ).get_or_create(
                character=self.obj,
            )
        return self._sheet_cache

    def _get_presented_appearance(self):
        """Map of FormTrait name -> presented display (descriptor or normalized), cached.

        The single source for appearance, shared with the web serializer via
        ``forms.services.get_presented_appearance``.
        """
        if self._presented_appearance_cache is None:
            from world.forms.services import get_presented_appearance

            self._presented_appearance_cache = {
                trait.trait_name: trait.display for trait in get_presented_appearance(self.obj)
            }
        return self._presented_appearance_cache

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

    def _get_personas(self):
        """Get character personas, with caching."""
        if self._personas_cache is None:
            from world.scenes.models import Persona

            self._personas_cache = list(
                Persona.objects.filter(character_sheet__character=self.obj).order_by(
                    "persona_type",
                    "name",
                ),
            )
        return self._personas_cache

    def get_primary_persona(self):
        """Get the character's primary persona."""
        from world.scenes.constants import PersonaType

        personas = self._get_personas()
        for persona in personas:
            if persona.persona_type == PersonaType.PRIMARY:
                return persona
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
        if sheet.gender:
            return sheet.gender.display_name
        return ""

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
        """Character's family name from sheet data."""
        sheet = self._get_sheet()
        if sheet.family:
            return sheet.family.name
        return ""

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
    def species(self):
        """Character's species from sheet data."""
        sheet = self._get_sheet()
        return sheet.species

    @property
    def race(self):
        """Character's race (alias for species) from sheet data."""
        # Backwards compatibility alias - prefer species
        return self.species

    @property
    def classes(self):
        """Character's class levels."""
        return self._get_classes()

    @property
    def personas(self):
        """Character's available personas."""
        return self._get_personas()

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
        self._presented_appearance_cache = None
        self._classes_cache = None
        self._personas_cache = None

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

    def get_persona_by_name(self, persona_name):
        """Get a specific persona by name."""
        personas = self._get_personas()
        for persona in personas:
            if persona.name.lower() == persona_name.lower():
                return persona
        return None

    def get_display_name(self, include_colored=True):
        """
        Get the appropriate display name with persona override support.

        Args:
            include_colored (bool): Whether to include colored names

        Returns:
            str: The most appropriate display name (persona name if active,
                 otherwise display data)
        """
        # Check for primary persona first
        primary_persona = self.get_primary_persona()
        if primary_persona:
            if include_colored and primary_persona.colored_name:
                return primary_persona.colored_name
            return primary_persona.name

        # Fall back to parent implementation (ObjectDisplayData)
        return super().get_display_name(include_colored=include_colored)

    def get_display_description(self):
        """The character's current display description (#2632 rewire).

        The parent read (ObjectDisplayData) wins when set — for characters
        that is the event-disguise ``temporary_description`` overlay, which
        must mask the real look. Otherwise the sheet's ``additional_desc``
        (the live free-text physical description: CG writes it, the Great
        Archive recorded-profile flow updates it). The old first stop —
        ``Persona.description`` — was a vestigial #347-era field nothing
        ever wrote; removed.
        """
        return super().get_display_description() or self.additional_desc

    @property
    def _sheet_handler(self):
        """Legacy property for test compatibility - returns the sheet cache."""
        return self._sheet_cache

    # Explicit characteristic properties that the sheet command expects
    @property
    def eye_color(self) -> str:
        """Character's eye color, presented (descriptor or normalized)."""
        return self._get_presented_appearance().get("eye_color", "")

    @property
    def hair_color(self) -> str:
        """Character's hair color, presented (descriptor or normalized)."""
        return self._get_presented_appearance().get("hair_color", "")

    @property
    def height(self) -> str:
        """Character's apparent height band display (e.g. 'Tall')."""
        from world.forms.services import get_apparent_height

        _inches, band = get_apparent_height(self.obj)
        return band.display_name if band else ""

    @property
    def skin_tone(self) -> str:
        """Character's skin tone, presented (descriptor or normalized)."""
        return self._get_presented_appearance().get("skin_tone", "")

    # Additional sheet properties that may be accessed directly
    @property
    def additional_desc(self) -> str:
        """Character's additional description from sheet."""
        sheet = self._get_sheet()
        return sheet.additional_desc or ""
