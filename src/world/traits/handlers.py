"""
Trait system handlers focused on high-performance caching.

The TraitHandler implements a multi-layer caching system similar to Arx I
for fast trait value lookups and updates. The primary purpose is caching
CharacterTraitValues with case-insensitive trait name lookups.

Stat modifiers (distinctions, conditions, equipment) are automatically applied
when getting trait values for stats (strength, dexterity, etc.), valued and
tapered in the stat lane (#4726).
"""

from collections import Counter, defaultdict
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

from world.traits.models import (
    CharacterTraitValue,
    PointConversionRange,
    Trait,
    TraitType,
    display_trait_value,
)

#: The trait types a ``ModifierTarget`` with ``target_trait`` set can modify (#4820). A
#: language or OTHER trait reads its stored value alone.
MODIFIABLE_TRAIT_TYPES: frozenset[str] = frozenset({TraitType.STAT, TraitType.SKILL})


class DefaultTraitValue:
    """
    Default trait value object returned when a trait isn't found.

    Similar to Arx I's pattern of returning empty objects instead of None
    to avoid constant None checking in gameplay code.
    """

    def __init__(self, trait_name: str = "", trait_type: str | None = None) -> None:
        self.trait_name = trait_name
        self.trait_type = trait_type
        self.value = 0

    @property
    def display_value(self) -> int:
        return 0

    def __str__(self) -> str:
        return f"Default: {self.trait_name} = 0"

    def __bool__(self) -> bool:
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

    def __init__(self, character: "ObjectDB") -> None:
        """Initialize handler for a specific character."""
        self.character = character

        # Multi-level cache organized by trait type for performance
        # Uses defaultdict to return DefaultTraitValue for missing traits
        # Note: cast() needed because Django TextChoices are tuples at runtime
        self._cache: dict[
            str,
            defaultdict[str, CharacterTraitValue | DefaultTraitValue],
        ] = {
            # One bucket per TraitType, never a hand-picked subset: a character holding a
            # trait of a type with no bucket (a LANGUAGE fluency, #2993) made every trait
            # read on that character raise KeyError (#4373).
            trait_type: defaultdict(
                lambda trait_type=trait_type: DefaultTraitValue("", trait_type),
            )
            for trait_type in TraitType.values
        }

        self.initialized = False

    def setup_cache(self, reset: bool = False) -> None:
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
        trait_values = CharacterTraitValue.objects.filter(
            character_id=self.character.pk
        ).select_related("trait")
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

        For stats (strength, dexterity, etc.) and skills (sailing, melee combat),
        this includes modifiers from distinctions like Giant's Blood or Sailor,
        in the trait's stored units: a +10 on a stat is +1.0 shown, a +10 on a
        skill is +10 shown (#4820). Advancement never reads this number; it reads
        the stored value, so a bonus never raises the cost of the next rank.

        Args:
            trait_name: Name of the trait to look up

        Returns:
            Current trait value with modifiers applied, or 0 if not set
        """
        base_value = self.get_base_trait_value(trait_name)

        trait = Trait.get_by_name(trait_name)
        if trait and trait.trait_type in MODIFIABLE_TRAIT_TYPES:
            return base_value + self.get_trait_modifier(trait)

        return base_value

    def get_trait_modifier(self, trait: "Trait") -> int:
        """The modifier ``get_trait_value`` adds to ``trait``'s stored value (#4820).

        Zero for a trait type nothing modifies (a language, OTHER) and for a stat or
        skill whose trait has no ``ModifierTarget`` yet. The character sheet reads
        this beside the stored value so a skill shows the number a roll uses.
        """
        if trait.trait_type not in MODIFIABLE_TRAIT_TYPES:
            return 0
        return self._get_stat_modifier(trait)

    def _get_stat_modifier(self, trait: "Trait") -> int:
        """
        Get the total modifier for a stat or skill, valued and tapered in the stat lane
        (#4726; skills join it in #4820).

        Uses the ModifierTarget.target_trait FK for type-safe lookup
        instead of string matching. Takes the already-resolved ``Trait``
        instance (from ``get_trait_value``'s cached ``get_by_name``) so no
        redundant ``Trait.objects.get(name__iexact=...)`` query fires, and
        resolves the ModifierTarget through ``ModifierTarget.get_for_trait``
        — a class-level cache keyed by ``target_trait_id`` — so neither the
        trait nor the target lookup re-queries per call. This kept fatigue
        capacity (which resolves 6 stat values per participant) from firing
        a per-stat N+1 on the combat detail hot path (#552).

        The total is a checks ``ModifierBreakdown`` over the stat target's CHARACTER,
        EQUIPMENT and CONDITION contributions, so a sized technique buff or distinction
        effect reads the stat lane's value table and a pile of one kind tapers by the
        stat lane's ``ModifierTaper`` rows. Every reader of ``get_trait_value`` (checks,
        fatigue, stamina, carrying capacity, scandal, the stat sheet) sees this one
        number. Hot path: the value table loads only when a source is sized, and the
        taper rules only when some kind has two or more contributions, so a read with
        nothing sized and no pile runs no query beyond the sources themselves.
        """
        from world.checks.constants import ModifierLane  # noqa: PLC0415
        from world.checks.modifier_values import load_taper_rules  # noqa: PLC0415
        from world.checks.services import modifier_target_contributions  # noqa: PLC0415
        from world.checks.types import ModifierBreakdown  # noqa: PLC0415
        from world.conditions.services import condition_target_contributions  # noqa: PLC0415
        from world.mechanics.models import ModifierTarget  # noqa: PLC0415

        sheet = self.character.character_sheet
        if sheet is None:
            return 0

        target = ModifierTarget.get_for_trait(trait)
        if target is None:
            return 0
        contributions = modifier_target_contributions(
            sheet, target, lane=ModifierLane.STAT
        ) + condition_target_contributions(sheet, target, lane=ModifierLane.STAT)
        kinds = Counter(contribution.source_kind for contribution in contributions)
        has_pile = any(count >= 2 for count in kinds.values())  # noqa: PLR2004
        tapers = load_taper_rules(ModifierLane.STAT) if has_pile else {}
        return ModifierBreakdown(contributions=contributions, tapers=tapers).total

    def get_trait_display_value(self, trait_name: str) -> int:
        """
        Get the display value for a trait (#2894): stats ÷10, skills true value.

        Args:
            trait_name: Name of the trait

        Returns:
            The value as players see it (modifiers included).
        """
        value = self.get_trait_value(trait_name)
        trait = Trait.get_by_name(trait_name)
        return display_trait_value(trait.trait_type if trait else TraitType.OTHER, value)

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
            character=self.character.sheet_data,
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

    def clear_cache(self) -> None:
        """Clear the trait cache and mark for reinitialization."""
        for trait_type_cache in self._cache.values():
            trait_type_cache.clear()
        self.initialized = False


# Global cache for character trait handlers
_character_trait_handlers: dict[int, "TraitHandler"] = {}
