"""
Arx II Traits System Models

Core models for character traits, check resolution, and advancement tracking.
Following Arx II design principles:
- 1-100 internal scale (displayed as 1.0-10.0)
- Data-driven configuration for all mechanics
- Support for GM/player intervention in checks
- Clean separation between trait definitions and character values
"""

from typing import TYPE_CHECKING, Any, ClassVar, Optional, cast

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.contributors.models import CreditedContent
from world.roster.models import RosterTenure

if TYPE_CHECKING:
    pass


class TraitChangeSource(models.TextChoices):
    """How a CharacterTraitValue's value came to change in place (#3055).

    Acquisition-provenance discriminator for CharacterTraitChange — the
    ``DistinctionOrigin`` pattern (``world.distinctions.types``) generalized to
    trait/skill value mutation. Every production writer that mutates an
    existing (or stamps a brand-new) ``CharacterTraitValue.value`` records one
    of these in the same transaction; a mutation with no matching row is a
    bug, not a silent gap. Defined here (not ``constants.py``) for the same
    reason ``TraitType``/``TraitCategory`` are — ``constants.py`` re-exports
    all three from this module to avoid a circular import.
    """

    CHARACTER_CREATION = "character_creation", "Character Creation"
    DEVELOPMENT_LEVEL_UP = "development_level_up", "Development Level-Up"
    MATURATION = "maturation", "Maturation"
    GM_GRANT = "gm_grant", "GM Grant"


class TraitType(models.TextChoices):
    """Classification of traits for different game mechanics."""

    STAT = "stat", "Stat"
    SKILL = "skill", "Skill"
    MODIFIER = "modifier", "Modifier"
    OTHER = "other", "Other"


# The stat display divisor (#2894, ADR-0193). STATS store internal ×10 (stat 2
# → stored 20) and display single-digit (÷10). SKILLS store and display their
# true 1-100 value — development moves them by single points (11…19) and XP
# unlocks cross the ×10 rung boundaries — so skill display is the stored value,
# never divided. Convert stat display at the edge with this divisor; never
# write a display-scale stat to CharacterTraitValue.
# (Defined here, not in constants.py, because constants.py imports this module;
# constants.py re-exports it.)
STAT_DISPLAY_DIVISOR = 10


def display_trait_value(trait_type: str, value: int) -> int:
    """A trait value as players see it: stats ÷10, everything else true value."""
    if trait_type == TraitType.STAT:
        return value // STAT_DISPLAY_DIVISOR
    return value


def _trait_type_label(trait_type: str) -> str:
    """Return the display label for a trait type."""
    try:
        return TraitType(trait_type).label
    except ValueError:
        return str(trait_type)


def _trait_category_label(category: str) -> str:
    """Return the display label for a trait category."""
    try:
        return TraitCategory(category).label
    except ValueError:
        return str(category)


class TraitCategory(models.TextChoices):
    """Trait categories for organization and special mechanics."""

    # Stat categories
    PHYSICAL = "physical", "Physical"
    SOCIAL = "social", "Social"
    MENTAL = "mental", "Mental"
    META = "meta", "Meta"
    MAGIC = "magic", "Magic"

    # Skill categories
    COMBAT = "combat", "Combat"
    GENERAL = "general", "General"
    CRAFTING = "crafting", "Crafting"
    WAR = "war", "War"

    # Other category
    OTHER = "other", "Other"


class Trait(NaturalKeyMixin, CreditedContent, SharedMemoryModel):
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
        blank=True,
        help_text="Optional description of what this trait represents",
    )
    is_public = models.BooleanField(
        default=True,
        help_text="Whether this trait should display by default in character sheets",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]
        # Small set of stats/skills read by name from handlers and predicates
        # everywhere — load it whole once (#2687).
        lookup_table = True

    class Meta:
        ordering = ["trait_type", "category", "name"]
        indexes = [
            models.Index(fields=["trait_type", "category"]),
            models.Index(fields=["is_public"]),
        ]

    def trait_type_display(self) -> str:
        """Return the display label for ``trait_type``."""
        return _trait_type_label(cast(str, self.trait_type))

    def category_display(self) -> str:
        """Return the display label for ``category``."""
        return _trait_category_label(cast(str, self.category))

    def __str__(self) -> str:
        return f"{self.name} ({self.trait_type_display()})"

    @classmethod
    def get_by_name(cls, name: str) -> Optional["Trait"]:
        """Get a trait by name (case-insensitive), or None if absent.

        Delegates to the generic natural-key index (#2687). ``Trait`` is a
        ``lookup_table``: a small set used everywhere, so the whole table loads
        once and every lookup after resolves from memory — the same
        one-query-then-free behaviour the hand-rolled ``_build_name_cache``
        provided, minus the bespoke cache.

        Returns None rather than raising, because callers branch on it
        (``world/traits/handlers.py``, ``world/predicates/predicates.py``).
        """
        try:
            return cast("Trait", cls.objects.get_by_natural_key(name))
        except cls.DoesNotExist:
            return None


class TraitRankDescription(NaturalKeyMixin, SharedMemoryModel):
    """
    Descriptive labels for trait values during character creation.

    Provides user-friendly names for specific trait values, allowing players
    to select "Strong" instead of seeing a slider with numbers.
    """

    trait = models.ForeignKey(
        Trait,
        on_delete=models.CASCADE,
        related_name="rank_descriptions",
    )
    value = models.IntegerField(help_text="Trait value this description applies to")
    label = models.CharField(
        max_length=100,
        unique=True,
        help_text="Descriptive name (can be lengthy and flowery)",
    )
    description = models.TextField(
        blank=True,
        help_text="Longer description of what this trait level means",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["trait", "value"]
        dependencies = ["arxii.Trait"]

    class Meta:
        unique_together = ["trait", "value"]
        ordering = ["trait", "value"]
        indexes = [
            models.Index(fields=["trait", "value"]),
        ]

    def __str__(self) -> str:
        return f"{self.trait.name}: {self.label} ({self.display_value})"

    @property
    def display_value(self) -> int:
        """Display value as shown to players: stats ÷10, skills true value (#2894)."""
        return display_trait_value(self.trait.trait_type, cast(int, self.value))


class CharacterTraitValue(SharedMemoryModel):
    """
    Actual trait values for characters with automatic cache updating.

    Links characters to their trait values. Values can be any integer
    (including negative) as some traits may have negative values or
    very high values for NPCs.

    Automatically updates the character's trait handler cache when modified.
    """

    character = models.ForeignKey(
        "arxii.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="trait_values",
    )
    trait = models.ForeignKey(
        Trait,
        on_delete=models.CASCADE,
        related_name="character_values",
    )
    value = models.IntegerField(help_text="Current trait value (can be any integer)")
    character_id: int

    class Meta:
        unique_together: ClassVar[list[list[str]]] = [["character", "trait"]]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["character", "trait"]),
            models.Index(fields=["character"]),
        ]

    def __str__(self) -> str:
        return f"{self.character}: {self.trait.name} = {self.display_value}"

    @property
    def display_value(self) -> int:
        """Display value as shown to players: stats ÷10, skills true value (#2894)."""
        return display_trait_value(self.trait.trait_type, cast(int, self.value))

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Override save to update character's trait handler cache."""
        super().save(*args, **kwargs)
        # Update the character's trait handler cache if it exists
        self._update_trait_cache()

    def delete(
        self, using: str | None = None, keep_parents: bool = False
    ) -> tuple[int, dict[str, int]]:
        """Override delete to update character's trait handler cache."""
        # Remove from character's trait handler cache if it exists
        self._update_trait_cache(remove=True)
        return super().delete(using=using, keep_parents=keep_parents)

    def _update_trait_cache(self, remove: bool = False) -> None:
        """Update the character's trait handler cache if it exists."""
        try:
            # Import here to avoid circular imports
            from world.traits.handlers import _character_trait_handlers

            character_id = self.character_id
            if character_id in _character_trait_handlers:
                handler = _character_trait_handlers[character_id]
                if remove:
                    handler.remove_trait_value_from_cache(self)
                else:
                    handler.add_trait_value_to_cache(self)
        except ImportError:
            # Handler not available during tests sometimes
            pass


class CharacterTraitChange(SharedMemoryModel):
    """Durable acquisition-provenance record for an in-place trait/skill value change (#3055).

    ``CharacterTraitValue.value`` mutates in place (a stat raised via
    development level-ups, the CG baseline stamp, a maturation spend, ...)
    and leaves no authored-value record of its own — unlike
    ``CharacterTechnique``/``CharacterGift`` (own ``origin`` field) or
    ``CharacterXPTransaction``/``ResonanceGrant``/``ClassLevelAdvancement``
    (already-adequate receipts). This is the missing record: every production
    writer of ``CharacterTraitValue.value`` creates one of these in the same
    transaction as the mutation, so pristine (CG/authoring) state can be
    derived from provenance rather than snapshotted, and a future GM story
    reward (source=GM_GRANT, #3055 slice 1c) has somewhere to stamp itself.
    """

    character_sheet = models.ForeignKey(
        "arxii.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="trait_changes",
        help_text="The character whose trait value changed.",
    )
    trait = models.ForeignKey(
        Trait,
        on_delete=models.CASCADE,
        related_name="character_changes",
        help_text="The trait whose value changed.",
    )
    old_value = models.IntegerField(
        help_text="The trait's internal-scale value before this change (0 for a brand-new "
        "CharacterTraitValue row that didn't exist yet).",
    )
    new_value = models.IntegerField(
        help_text="The trait's internal-scale value after this change.",
    )
    source = models.CharField(
        max_length=30,
        choices=TraitChangeSource.choices,
        help_text="How this value change came about.",
    )
    granting_tenure = models.ForeignKey(
        RosterTenure,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="granted_trait_changes",
        help_text="The GM's tenure that granted this change, when source=GM_GRANT (#3055 "
        "slice 1c). Null for every automatic/self-driven source. PROTECT: tenures are "
        "never deleted post-release (mirrors Discovery.discovered_by_tenure, #3060).",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-created_at"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["character_sheet", "-created_at"]),
        ]
        verbose_name = "Character Trait Change"
        verbose_name_plural = "Character Trait Changes"

    def __str__(self) -> str:
        return (
            f"{self.character_sheet}: {self.trait.name} "
            f"{self.old_value}->{self.new_value} ({self.source})"
        )


# Check Resolution System Models


class PointConversionRange(NaturalKeyMixin, SharedMemoryModel):
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
        help_text="Minimum trait value for this range (inclusive)",
    )
    max_value = models.IntegerField(
        help_text="Maximum trait value for this range (inclusive)",
    )
    points_per_level = models.SmallIntegerField(
        help_text="Points awarded per trait level in this range",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["trait_type", "min_value"]

    class Meta:
        ordering: ClassVar[list[str]] = ["trait_type", "min_value"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["trait_type", "min_value"]),
        ]

    def __str__(self) -> str:
        return (
            f"{_trait_type_label(cast(str, self.trait_type))} {self.min_value}-{self.max_value}: "
            f"{self.points_per_level} pts/level"
        )

    def clean(self) -> None:
        """Validate range and check for overlaps."""
        super().clean()
        if self.min_value > self.max_value:
            msg = "min_value must be <= max_value"
            raise ValidationError(msg)

        if self.trait_type:
            # Check for overlapping ranges
            overlapping = PointConversionRange.objects.filter(
                trait_type=self.trait_type,
            )
            if self.pk:
                overlapping = overlapping.exclude(pk=self.pk)

            for other_range in overlapping:
                if (
                    self.min_value <= other_range.max_value
                    and self.max_value >= other_range.min_value
                ):
                    msg = (
                        f"Range {self.min_value}-{self.max_value} overlaps with "
                        f"existing range {other_range.min_value}-"
                        f"{other_range.max_value}"
                    )
                    raise ValidationError(
                        msg,
                    )

    def contains_value(self, value: int) -> bool:
        """Check if a value falls within this range."""
        return self.min_value <= value <= self.max_value

    @classmethod
    def calculate_points(cls, trait_type: str, trait_value: int) -> int:
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
                    conversion_range.min_value,
                    1,
                )  # Start at 1 or range min
                end_in_range = min(conversion_range.max_value, trait_value)

                if end_in_range >= start_in_range:
                    levels_in_range = end_in_range - start_in_range + 1
                    total_points += levels_in_range * conversion_range.points_per_level
            elif trait_value > conversion_range.max_value:
                # This entire range is below our value, count all levels
                levels_in_range = conversion_range.max_value - conversion_range.min_value + 1
                total_points += levels_in_range * conversion_range.points_per_level
            else:
                # trait_value < conversion_range.min_value, we're done
                break

        return total_points


class CheckRank(NaturalKeyMixin, SharedMemoryModel):
    """
    Maps point totals to rank levels for check resolution.

    Based on Arx I's CheckRank system with exponential thresholds.
    Uses caching for performance.
    """

    rank = models.SmallIntegerField(
        unique=True,
        help_text="Rank level (0 = weakest, higher = stronger)",
    )
    min_points = models.PositiveIntegerField(
        help_text="Minimum points needed to achieve this rank",
    )
    name = models.CharField(
        max_length=50,
        help_text="Descriptive name for this rank level",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of what this rank represents",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["rank"]

    class Meta:
        ordering: ClassVar[list[str]] = ["rank"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["rank"]),
            models.Index(fields=["min_points"]),
        ]

    def __str__(self) -> str:
        return f"Rank {self.rank}: {self.name} ({self.min_points}+ pts)"

    @classmethod
    def get_rank_for_points(cls, points: int) -> Optional["CheckRank"]:
        """Get the highest rank achievable with the given points."""
        return cls.objects.filter(min_points__lte=points).order_by("-rank").first()

    @classmethod
    def get_rank_difference(cls, roller_points: int, target_points: int) -> int:
        """Calculate rank difference between roller and target."""
        roller_rank = cls.get_rank_for_points(roller_points)
        target_rank = cls.get_rank_for_points(target_points)

        if not roller_rank or not target_rank:
            return 0

        return roller_rank.rank - target_rank.rank


class CheckOutcome(NaturalKeyMixin, SharedMemoryModel):
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
        blank=True,
        help_text="Description of what this outcome means",
    )
    success_level = models.SmallIntegerField(
        default=0,
        help_text="Numeric success level (-10 worst failure to +10 best success)",
    )
    display_template = models.TextField(
        blank=True,
        help_text="Optional template for displaying this outcome",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        ordering: ClassVar[list[str]] = ["success_level", "name"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["success_level"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} (level {self.success_level})"


class ResultChart(NaturalKeyMixin, SharedMemoryModel):
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
        max_length=50,
        help_text="Descriptive name for this difficulty level",
    )

    # Cache for chart lookups
    _chart_cache: ClassVar[dict[int, "ResultChart"]] = {}

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["rank_difference"]

    class Meta:
        ordering: ClassVar[list[str]] = ["rank_difference"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["rank_difference"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} (rank diff {self.rank_difference:+d})"

    @classmethod
    def get_chart_for_difference(cls, rank_difference: int) -> Optional["ResultChart"]:
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
    def _build_chart_cache(cls) -> None:
        """Build the chart cache dictionary."""
        cls._chart_cache = {chart.rank_difference: chart for chart in cls.objects.all()}

    @classmethod
    def clear_cache(cls) -> None:
        """Clear the chart cache (call when charts are modified)."""
        cls._chart_cache = {}


class ResultChartOutcome(NaturalKeyMixin, SharedMemoryModel):
    """
    Individual outcome ranges within a result chart.

    Defines the 0-100 roll ranges and their associated outcomes.
    Links to CheckOutcome for consistent outcome definitions.
    """

    chart = models.ForeignKey(
        ResultChart,
        on_delete=models.CASCADE,
        related_name="outcomes",
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

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["chart", "min_roll"]
        dependencies = ["arxii.ResultChart"]

    class Meta:
        ordering: ClassVar[list[str]] = ["chart", "min_roll"]
        unique_together: ClassVar[list[list[str]]] = [["chart", "min_roll"]]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["chart", "min_roll"]),
        ]

    def __str__(self) -> str:
        return f"{self.chart.name}: {self.outcome.name} ({self.min_roll}-{self.max_roll})"

    def clean(self) -> None:
        """Validate roll range is valid."""
        super().clean()
        if self.min_roll > self.max_roll:
            msg = "min_roll must be <= max_roll"
            raise ValidationError(msg)

    def contains_roll(self, roll: int) -> bool:
        """Check if a roll falls within this outcome's range."""
        return self.min_roll <= roll <= self.max_roll
