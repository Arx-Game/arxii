"""
Trait system handlers focused on high-performance caching.

The TraitHandler implements a multi-layer caching system similar to Arx I
for fast trait value lookups and updates. The primary purpose is caching
CharacterTraitValues with case-insensitive trait name lookups.

Stat modifiers from distinctions are automatically applied when getting
trait values for stats (strength, dexterity, etc.).
"""

from collections import defaultdict
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

from world.traits.models import (
    CharacterTraitValue,
    PointConversionRange,
    Trait,
    TraitType,
)


class DefaultTraitValue:
    """
    Default trait value object returned when a trait isn't found.

    Similar to Arx I's pattern of returning empty objects instead of None
    to avoid constant None checking in gameplay code.
    """

    def __init__(self, trait_name="", trait_type=None):
        self.trait_name = trait_name
        self.trait_type = trait_type
        self.value = 0

    @property
    def display_value(self):
        return 0.0

    def __str__(self):
        return f"Default: {self.trait_name} = 0"

    def __bool__(self):
        return False


class TraitHandler:
    """
    High-performance trait handler with multi-layer caching.

    Primary responsibilities:
    1. Cache CharacterTraitValues in memory for fast lookup
    2. Provide case-insensitive trait name lookups
    3. Automatically update cache when traits are modified
    4. Return default values instead of None for missing traits

    Caching strategy follows Arx I pattern:
    - Lazy initialization of cache
    - Case-insensitive trait name keys
    - Defaultdict pattern for graceful missing trait handling
    - Automatic cache updates on model saves
    """

    def __init__(self, character: "ObjectDB"):
        """Initialize handler for a specific character."""
        self.character = character

        # Multi-level cache organized by trait type for performance
        # Uses defaultdict to return DefaultTraitValue for missing traits
        # Note: cast() needed because Django TextChoices are tuples at runtime
        self._cache: dict[
            str,
            defaultdict[str, CharacterTraitValue | DefaultTraitValue],
        ] = {
            cast(str, TraitType.STAT): defaultdict(
                lambda: DefaultTraitValue("", TraitType.STAT),
            ),
            cast(str, TraitType.SKILL): defaultdict(
                lambda: DefaultTraitValue("", TraitType.SKILL),
            ),
            cast(str, TraitType.OTHER): defaultdict(
                lambda: DefaultTraitValue("", TraitType.OTHER),
            ),
        }

        self.initialized = False

    def setup_cache(self, reset=False):
        """
        Initialize or reset the trait value cache.

        Args:
            reset: If True, clear and rebuild the entire cache
        """
        if not reset and self.initialized:
            return

        # Clear cache if resetting
        if reset:
            for trait_type_cache in self._cache.values():
                trait_type_cache.clear()

        # Load all trait values for this character and populate cache
        character = cast(Any, self.character)
        trait_values = character.trait_values.select_related("trait").all()
        for trait_value in trait_values:
            self.add_trait_value_to_cache(trait_value)

        self.initialized = True

    def add_trait_value_to_cache(self, trait_value: CharacterTraitValue) -> None:
        """
        Add or update a trait value in the cache.

        Args:
            trait_value: CharacterTraitValue instance to cache
        """
        trait = cast(Trait, trait_value.trait)
        trait_type = cast(str, trait.trait_type)
        trait_name = cast(str, trait.name)
        trait_name_lower = trait_name.lower()

        # Store in appropriate trait type cache with case-insensitive key
        self._cache[trait_type][trait_name_lower] = trait_value

    def remove_trait_value_from_cache(self, trait_value: CharacterTraitValue) -> None:
        """
        Remove a trait value from the cache.

        Args:
            trait_value: CharacterTraitValue instance to remove
        """
        trait = cast(Trait, trait_value.trait)
        trait_type = cast(str, trait.trait_type)
        trait_name = cast(str, trait.name)
        trait_name_lower = trait_name.lower()

        # Remove from cache if it exists
        if trait_name_lower in self._cache[trait_type]:
            del self._cache[trait_type][trait_name_lower]

    def get_base_trait_value(self, trait_name: str) -> int:
        """
        Get the base value of a trait without modifiers (case-insensitive).

        Args:
            trait_name: Name of the trait to look up

        Returns:
            Base trait value, or 0 if not set
        """
        self.setup_cache()

        trait_name_lower = trait_name.lower()

        # Search through all trait type caches
        for trait_type_cache in self._cache.values():
            if trait_name_lower in trait_type_cache:
                trait_value = trait_type_cache[trait_name_lower]
                if isinstance(trait_value, CharacterTraitValue):
                    return cast(int, trait_value.value)
                # DefaultTraitValue also has a .value attribute
                return cast(int, trait_value.value)

        return 0

    def get_trait_value(self, trait_name: str) -> int:
        """
        Get the current value of a trait including modifiers (case-insensitive).

        For stats (strength, dexterity, etc.), this includes modifiers from
        distinctions like Giant's Blood. Modifiers are scaled appropriately
        (modifier value of 10 = 1.0 display value = 10 internal).

        Args:
            trait_name: Name of the trait to look up

        Returns:
            Current trait value with modifiers applied, or 0 if not set
        """
        base_value = self.get_base_trait_value(trait_name)

        # Check if this is a stat that might have modifiers
        trait = Trait.get_by_name(trait_name)
        if trait and trait.trait_type == TraitType.STAT:
            modifier = self._get_stat_modifier(trait_name.lower())
            return base_value + modifier

        return base_value

    def _get_stat_modifier(self, stat_name: str) -> int:
        """
        Get the total modifier for a stat from character's distinctions etc.

        Args:
            stat_name: Lowercase stat name (e.g., "strength")

        Returns:
            Total modifier value (can be negative). Returns 0 if no sheet or modifiers.
            Modifier is in internal scale (10 = 1.0 display value).
        """
        # Import here to avoid circular imports
        from world.mechanics.services import (  # noqa: PLC0415
            get_modifier_for_character,
        )

        return get_modifier_for_character(self.character, "stat", stat_name)

    def get_trait_display_value(self, trait_name: str) -> float:
        """
        Get the display value (1.0-10.0 scale) for a trait.

        Args:
            trait_name: Name of the trait

        Returns:
            Display value rounded to 1 decimal place
        """
        value = self.get_trait_value(trait_name)
        return round(value / 10, 1)

    def set_trait_value(self, trait_name: str, value: int) -> bool:
        """
        Set a trait value for this character with cache update.

        Args:
            trait_name: Name of the trait to set
            value: New value to set

        Returns:
            True if successful, False if trait doesn't exist
        """
        trait = Trait.get_by_name(trait_name)
        if not trait:
            return False

        # Create or update the trait value
        trait_value, created = CharacterTraitValue.objects.get_or_create(
            character=self.character,
            trait=trait,
            defaults={"value": value},
        )

        if not created:
            trait_value.value = value
            trait_value.save()

        # Cache will be automatically updated by the model's save method
        return True

    def get_trait_object(
        self,
        trait_name: str,
    ) -> CharacterTraitValue | DefaultTraitValue:
        """
        Get the CharacterTraitValue object for a trait (case-insensitive).

        Args:
            trait_name: Name of the trait to look up

        Returns:
            CharacterTraitValue object or DefaultTraitValue if not found
        """
        self.setup_cache()

        trait_name_lower = trait_name.lower()

        # Search through all trait type caches
        for trait_type_cache in self._cache.values():
            trait_value = trait_type_cache[trait_name_lower]
            if isinstance(trait_value, CharacterTraitValue):
                return trait_value

        # Return default value object
        return DefaultTraitValue(trait_name, "")

    def get_traits_by_type(self, trait_type: str) -> dict[str, CharacterTraitValue]:
        """
        Get all traits of a specific type.

        Args:
            trait_type: TraitType to filter by

        Returns:
            Dictionary mapping trait names to CharacterTraitValue objects
        """
        self.setup_cache()

        result: dict[str, CharacterTraitValue] = {}
        trait_type_cache: defaultdict[
            str,
            CharacterTraitValue | DefaultTraitValue,
        ] = self._cache.get(
            trait_type,
            defaultdict(lambda: DefaultTraitValue("", trait_type)),
        )

        for trait_value in trait_type_cache.values():
            if isinstance(trait_value, CharacterTraitValue):
                trait = cast(Trait, trait_value.trait)
                result[cast(str, trait.name)] = trait_value

        return result

    def get_all_traits(self) -> dict[str, dict[str, CharacterTraitValue]]:
        """
        Get all trait values organized by category with caching.

        Returns:
            Dictionary with trait categories as keys, containing
            CharacterTraitValue instances
        """
        self.setup_cache()

        result: dict[str, dict[str, CharacterTraitValue]] = {}

        for trait_type_cache in self._cache.values():
            for trait_value in trait_type_cache.values():
                if isinstance(trait_value, CharacterTraitValue):
                    trait = cast(Trait, trait_value.trait)
                    category = trait.category_display()

                    if category not in result:
                        result[category] = {}

                    result[category][cast(str, trait.name)] = trait_value

        return result

    def get_public_traits(self) -> dict[str, dict[str, CharacterTraitValue]]:
        """
        Get only public traits (those that should display by default).

        Returns:
            Dictionary with trait categories as keys, containing public
            CharacterTraitValue instances
        """
        all_traits = self.get_all_traits()

        result: dict[str, dict[str, CharacterTraitValue]] = {}
        for category, traits in all_traits.items():
            for trait_name, trait_value in traits.items():
                trait = cast(Trait, trait_value.trait)
                if cast(bool, trait.is_public):
                    if category not in result:
                        result[category] = {}
                    result[category][trait_name] = trait_value

        return result

    def calculate_check_points(self, trait_names: list[str]) -> int:
        """
        Calculate total weighted points for a list of traits using cache.

        Args:
            trait_names: List of trait names to include in calculation

        Returns:
            Total weighted points
        """
        self.setup_cache()
        total_points = 0

        for trait_name in trait_names:
            trait_value = self.get_trait_value(trait_name)
            if trait_value > 0:
                trait = Trait.get_by_name(trait_name)
                if trait:
                    points = PointConversionRange.calculate_points(
                        trait.trait_type,
                        trait_value,
                    )
                    total_points += points

        return total_points

    def clear_cache(self):
        """Clear the trait cache and mark for reinitialization."""
        for trait_type_cache in self._cache.values():
            trait_type_cache.clear()
        self.initialized = False


# Global cache for character trait handlers
_character_trait_handlers: dict[int, "TraitHandler"] = {}
