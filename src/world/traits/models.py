"""
Arx II Traits System Models

Core models for character traits, check resolution, and advancement tracking.
Following Arx II design principles:
- 1-100 internal scale (displayed as 1.0-10.0)
- Data-driven configuration for all mechanics
- Support for GM/player intervention in checks
- Clean separation between trait definitions and character values
"""

from typing import Dict

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel


class TraitType(models.TextChoices):
    """Classification of traits for different game mechanics."""

    STAT = "stat", "Stat"
    SKILL = "skill", "Skill"
    OTHER = "other", "Other"


class TraitCategory(models.TextChoices):
    """Trait categories for organization and special mechanics."""

    # Stat categories
    PHYSICAL = "physical", "Physical"
    SOCIAL = "social", "Social"
    MENTAL = "mental", "Mental"
    MAGIC = "magic", "Magic"

    # Skill categories
    COMBAT = "combat", "Combat"
    GENERAL = "general", "General"
    CRAFTING = "crafting", "Crafting"

    # Other category
    OTHER = "other", "Other"


class Trait(SharedMemoryModel):
    """
    Trait definition template with case-insensitive caching.

    Defines the available traits that characters can have values in.
    Uses SharedMemoryModel for automatic caching and includes case-insensitive
    lookup methods similar to Arx I's NameLookupModel pattern.
    """

    name = models.CharField(
        max_length=50,
        unique=True,
        help_text="Trait name (e.g., 'strength', 'sewing', 'weaponsmithing')",
    )
    trait_type = models.CharField(
        max_length=10,
        choices=TraitType.choices,
        help_text="Classification of trait for mechanics and advancement",
    )
    category = models.CharField(
        max_length=20,
        choices=TraitCategory.choices,
        help_text="Category for organization and special rules",
    )

    # Metadata
    description = models.TextField(
        blank=True, help_text="Optional description of what this trait represents"
    )
    is_public = models.BooleanField(
        default=True,
        help_text="Whether this trait should display by default in character sheets",
    )

    # Caching for case-insensitive lookups
    _name_cache_built = False
    _name_to_trait_map: Dict[str, "Trait"] = {}

    class Meta:
        ordering = ["trait_type", "category", "name"]
        indexes = [
            models.Index(fields=["trait_type", "category"]),
            models.Index(fields=["is_public"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_trait_type_display()})"

    @classmethod
    def get_by_name(cls, name):
        """
        Get a trait by name with case-insensitive lookup and caching.

        Args:
            name: Trait name to look up (case-insensitive)

        Returns:
            Trait instance or None if not found
        """
        if not cls._name_cache_built:
            cls._build_name_cache()

        return cls._name_to_trait_map.get(name.lower())

    @classmethod
    def _build_name_cache(cls):
        """Build the name-to-trait mapping cache."""
        cls._name_to_trait_map = {}
        # Use SharedMemoryModel's caching to get all traits
        for trait in cls.get_all_cached_instances():
            cls._name_to_trait_map[trait.name.lower()] = trait
        cls._name_cache_built = True

    @classmethod
    def clear_name_cache(cls):
        """Clear the name cache (call when traits are modified)."""
        cls._name_cache_built = False
        cls._name_to_trait_map = {}

    def save(self, *args, **kwargs):
        """Override save to clear name cache when traits are modified."""
        super().save(*args, **kwargs)
        self.__class__.clear_name_cache()


class TraitRankDescription(SharedMemoryModel):
    """
    Descriptive labels for trait values during character creation.

    Provides user-friendly names for specific trait values, allowing players
    to select "Strong" instead of seeing a slider with numbers.
    """

    trait = models.ForeignKey(
        Trait, on_delete=models.CASCADE, related_name="rank_descriptions"
    )
    value = models.IntegerField(help_text="Trait value this description applies to")
    label = models.CharField(
        max_length=100,
        unique=True,
        help_text="Descriptive name (can be lengthy and flowery)",
    )
    description = models.TextField(
        blank=True, help_text="Longer description of what this trait level means"
    )

    class Meta:
        unique_together = ["trait", "value"]
        ordering = ["trait", "value"]
        indexes = [
            models.Index(fields=["trait", "value"]),
        ]

    def __str__(self):
        return f"{self.trait.name}: {self.label} ({self.display_value})"

    @property
    def display_value(self):
        """Display value as shown to players (e.g., 2.0 for value 20)."""
        return round(self.value / 10, 1)


class CharacterTraitValue(SharedMemoryModel):
    """
    Actual trait values for characters with automatic cache updating.

    Links characters to their trait values. Values can be any integer
    (including negative) as some traits may have negative values or
    very high values for NPCs.

    Automatically updates the character's trait handler cache when modified.
    """

    character = models.ForeignKey(
        "objects.ObjectDB", on_delete=models.CASCADE, related_name="trait_values"
    )
    trait = models.ForeignKey(
        Trait, on_delete=models.CASCADE, related_name="character_values"
    )
    value = models.IntegerField(help_text="Current trait value (can be any integer)")

    class Meta:
        unique_together = ["character", "trait"]
        indexes = [
            models.Index(fields=["character", "trait"]),
            models.Index(fields=["character"]),
        ]

    def __str__(self):
        return f"{self.character.key}: {self.trait.name} = {self.display_value}"

    @property
    def display_value(self):
        """Display value as shown to players (e.g., 2.5 for value 25)."""
        return round(self.value / 10, 1)

    def save(self, *args, **kwargs):
        """Override save to update character's trait handler cache."""
        super().save(*args, **kwargs)
        # Update the character's trait handler cache if it exists
        self._update_trait_cache()

    def delete(self, *args, **kwargs):
        """Override delete to update character's trait handler cache."""
        # Remove from character's trait handler cache if it exists
        self._update_trait_cache(remove=True)
        super().delete(*args, **kwargs)

    def _update_trait_cache(self, remove=False):
        """Update the character's trait handler cache if it exists."""
        try:
            # Import here to avoid circular imports
            from world.traits.handlers import _character_trait_handlers

            character_id = self.character.id
            if character_id in _character_trait_handlers:
                handler = _character_trait_handlers[character_id]
                if remove:
                    handler.remove_trait_value_from_cache(self)
                else:
                    handler.add_trait_value_to_cache(self)
        except ImportError:
            # Handler not available during tests sometimes
            pass


# Check Resolution System Models


class PointConversionRange(SharedMemoryModel):
    """
    Configurable lookup ranges for converting trait values to weighted points.

    Based on Arx I's successful StatWeight system. Uses explicit ranges
    with validation to prevent overlaps for the same trait type.
    """

    trait_type = models.CharField(
        max_length=10,
        choices=TraitType.choices,
        help_text="Type of trait this conversion applies to",
    )
    min_value = models.IntegerField(
        help_text="Minimum trait value for this range (inclusive)"
    )
    max_value = models.IntegerField(
        help_text="Maximum trait value for this range (inclusive)"
    )
    points_per_level = models.SmallIntegerField(
        help_text="Points awarded per trait level in this range"
    )

    class Meta:
        ordering = ["trait_type", "min_value"]
        indexes = [
            models.Index(fields=["trait_type", "min_value"]),
        ]

    def __str__(self):
        return (
            f"{self.get_trait_type_display()} {self.min_value}-{self.max_value}: "
            f"{self.points_per_level} pts/level"
        )

    def clean(self):
        """Validate range and check for overlaps."""
        super().clean()
        if self.min_value > self.max_value:
            raise ValidationError("min_value must be <= max_value")

        if self.trait_type:
            # Check for overlapping ranges
            overlapping = PointConversionRange.objects.filter(
                trait_type=self.trait_type
            )
            if self.pk:
                overlapping = overlapping.exclude(pk=self.pk)

            for other_range in overlapping:
                if (
                    self.min_value <= other_range.max_value
                    and self.max_value >= other_range.min_value
                ):
                    raise ValidationError(
                        f"Range {self.min_value}-{self.max_value} overlaps with "
                        f"existing range {other_range.min_value}-{other_range.max_value}"
                    )

    def contains_value(self, value):
        """Check if a value falls within this range."""
        return self.min_value <= value <= self.max_value

    @classmethod
    def calculate_points(cls, trait_type, trait_value):
        """
        Calculate total points for a trait value using the conversion ranges.

        If no range covers the value, returns 0 (this may indicate a gap
        in the configuration that should be addressed).
        """
        total_points = 0
        ranges = cls.objects.filter(trait_type=trait_type).order_by("min_value")

        for conversion_range in ranges:
            if conversion_range.contains_value(trait_value):
                # Find how many levels of this trait fall within this range
                start_in_range = max(
                    conversion_range.min_value, 1
                )  # Start at 1 or range min
                end_in_range = min(conversion_range.max_value, trait_value)

                if end_in_range >= start_in_range:
                    levels_in_range = end_in_range - start_in_range + 1
                    total_points += levels_in_range * conversion_range.points_per_level
            elif trait_value > conversion_range.max_value:
                # This entire range is below our value, count all levels
                levels_in_range = (
                    conversion_range.max_value - conversion_range.min_value + 1
                )
                total_points += levels_in_range * conversion_range.points_per_level
            else:
                # trait_value < conversion_range.min_value, we're done
                break

        return total_points


class CheckRank(SharedMemoryModel):
    """
    Maps point totals to rank levels for check resolution.

    Based on Arx I's CheckRank system with exponential thresholds.
    Uses caching for performance.
    """

    rank = models.SmallIntegerField(
        unique=True, help_text="Rank level (0 = weakest, higher = stronger)"
    )
    min_points = models.PositiveIntegerField(
        help_text="Minimum points needed to achieve this rank"
    )
    name = models.CharField(
        max_length=50, help_text="Descriptive name for this rank level"
    )
    description = models.TextField(
        blank=True, help_text="Description of what this rank represents"
    )

    class Meta:
        ordering = ["rank"]
        indexes = [
            models.Index(fields=["rank"]),
            models.Index(fields=["min_points"]),
        ]

    def __str__(self):
        return f"Rank {self.rank}: {self.name} ({self.min_points}+ pts)"

    @classmethod
    def get_rank_for_points(cls, points):
        """Get the highest rank achievable with the given points."""
        return cls.objects.filter(min_points__lte=points).order_by("-rank").first()

    @classmethod
    def get_rank_difference(cls, roller_points, target_points):
        """Calculate rank difference between roller and target."""
        roller_rank = cls.get_rank_for_points(roller_points)
        target_rank = cls.get_rank_for_points(target_points)

        if not roller_rank or not target_rank:
            return 0

        return roller_rank.rank - target_rank.rank


class CheckOutcome(SharedMemoryModel):
    """
    Defines possible check outcomes with names, descriptions, and display templates.

    Based on Arx I's outcome system. Outcomes can have templates for how
    they display to provide consistent messaging.
    """

    name = models.CharField(
        max_length=50,
        unique=True,
        help_text="Outcome name (e.g., 'Success', 'Catastrophic Failure')",
    )
    description = models.TextField(
        blank=True, help_text="Description of what this outcome means"
    )
    success_level = models.SmallIntegerField(
        default=0,
        help_text="Numeric success level (-10 worst failure to +10 best success)",
    )
    display_template = models.TextField(
        blank=True, help_text="Optional template for displaying this outcome"
    )

    class Meta:
        ordering = ["success_level", "name"]
        indexes = [
            models.Index(fields=["success_level"]),
        ]

    def __str__(self):
        return f"{self.name} (level {self.success_level})"


class ResultChart(SharedMemoryModel):
    """
    0-100 result charts for different difficulty levels.

    Based on Arx I's DifficultyTable system. Chart selection based on
    rank difference between roller and target. Uses caching for performance.
    """

    rank_difference = models.SmallIntegerField(
        unique=True,
        help_text="Rank difference this chart applies to (roller rank - target rank)",
    )
    name = models.CharField(
        max_length=50, help_text="Descriptive name for this difficulty level"
    )

    # Cache for chart lookups
    _chart_cache: Dict[int, "ResultChart"] = {}

    class Meta:
        ordering = ["rank_difference"]
        indexes = [
            models.Index(fields=["rank_difference"]),
        ]

    def __str__(self):
        return f"{self.name} (rank diff {self.rank_difference:+d})"

    @classmethod
    def get_chart_for_difference(cls, rank_difference):
        """
        Get the appropriate result chart for a rank difference.
        Uses caching to avoid repeated database queries.
        """
        if not cls._chart_cache:
            # Build cache on first access
            cls._build_chart_cache()

        # Try exact match first
        if rank_difference in cls._chart_cache:
            return cls._chart_cache[rank_difference]

        # Find closest chart
        available_diffs = sorted(cls._chart_cache.keys())
        if not available_diffs:
            return None

        # Find the closest rank difference
        closest_diff = min(available_diffs, key=lambda x: abs(x - rank_difference))
        return cls._chart_cache[closest_diff]

    @classmethod
    def _build_chart_cache(cls):
        """Build the chart cache dictionary."""
        cls._chart_cache = {chart.rank_difference: chart for chart in cls.objects.all()}

    @classmethod
    def clear_cache(cls):
        """Clear the chart cache (call when charts are modified)."""
        cls._chart_cache = {}


class ResultChartOutcome(SharedMemoryModel):
    """
    Individual outcome ranges within a result chart.

    Defines the 0-100 roll ranges and their associated outcomes.
    Links to CheckOutcome for consistent outcome definitions.
    """

    chart = models.ForeignKey(
        ResultChart, on_delete=models.CASCADE, related_name="outcomes"
    )
    min_roll = models.SmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text="Minimum roll (1-100) for this outcome",
    )
    max_roll = models.SmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text="Maximum roll (1-100) for this outcome",
    )
    outcome = models.ForeignKey(
        CheckOutcome,
        on_delete=models.CASCADE,
        help_text="The outcome that occurs for rolls in this range",
    )

    class Meta:
        ordering = ["chart", "min_roll"]
        unique_together = ["chart", "min_roll"]
        indexes = [
            models.Index(fields=["chart", "min_roll"]),
        ]

    def __str__(self):
        return (
            f"{self.chart.name}: {self.outcome.name} ({self.min_roll}-{self.max_roll})"
        )

    def clean(self):
        """Validate roll range is valid."""
        super().clean()
        if self.min_roll > self.max_roll:
            raise ValidationError("min_roll must be <= max_roll")

    def contains_roll(self, roll):
        """Check if a roll falls within this outcome's range."""
        return self.min_roll <= roll <= self.max_roll
