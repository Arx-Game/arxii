"""
Arx II Character Classes System Models

Models for character classes and class progression.
Following Arx II design principles:
- Data-driven configuration for class mechanics
- Support for elite classes that combine base classes
- Flexible trait requirements system
- Clean separation between class definitions and character assignments
"""

from functools import cached_property

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin


class PathStage(models.IntegerChoices):
    """Evolution stages for character paths."""

    QUIESCENT = 1, "Quiescent"  # Level 1 - non-magical, selected in CG
    POTENTIAL = 2, "Potential"  # Level 3 - awakening potential
    PUISSANT = 3, "Puissant"  # Level 6 - magical power
    TRUE = 4, "True"  # Level 11 - true mastery
    GRAND = 5, "Grand"  # Level 16 - grand power
    TRANSCENDENT = 6, "Transcendent"  # Level 21+ - beyond mortal


class Path(NaturalKeyMixin, SharedMemoryModel):
    """
    Character path definition with evolution hierarchy.

    Paths are the narrative-focused class system for Arx II, tracing a
    character's journey toward greatness through acts, legend, and achievements.
    """

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Path name (e.g., 'Path of Steel', 'Vanguard')",
    )
    description = models.TextField(
        help_text="Lore and flavor text describing this path",
    )
    stage = models.PositiveSmallIntegerField(
        choices=PathStage.choices,
        help_text="Evolution stage (Quiescent, Potential, Puissant, etc.)",
    )
    minimum_level = models.PositiveSmallIntegerField(
        help_text="Minimum character level to enter this path (1, 3, 6, 11, 16, 21 typical)",
    )

    # Evolution hierarchy - which lower-stage paths can evolve into this
    parent_paths = models.ManyToManyField(
        "self",
        symmetrical=False,
        blank=True,
        related_name="child_paths",
        help_text="Paths that can evolve into this one",
    )

    is_active = models.BooleanField(
        default=True,
        help_text="Whether this path is available for selection",
    )
    icon_url = models.URLField(
        blank=True,
        help_text="URL for path icon/image",
    )
    sort_order = models.PositiveSmallIntegerField(
        default=0,
        help_text="Display order within stage (lower = first)",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        ordering = ["stage", "sort_order", "name"]
        verbose_name = "Path"
        verbose_name_plural = "Paths"

    def __str__(self):
        return f"{self.name} ({self.get_stage_display()})"

    @cached_property
    def cached_path_aspects(self) -> list["PathAspect"]:
        """
        Get path aspects with related aspects loaded.

        This cached_property serves as the target for Prefetch(..., to_attr=).
        When prefetched, Django populates this directly. When accessed without
        prefetch, falls back to a fresh query.

        To invalidate: del instance.cached_path_aspects

        Note: This avoids SharedMemoryModel cache pollution - prefetch_related
        on SharedMemoryModel can pollute .all() cache permanently. Using to_attr
        with a cached_property gives explicit control over cache invalidation.
        """
        return list(self.path_aspects.select_related("aspect").all())


class CharacterClass(NaturalKeyMixin, SharedMemoryModel):
    """
    Character class definition with trait requirements and progression rules.

    Defines available classes that characters can have. Uses SharedMemoryModel
    for automatic caching and performance optimization.
    """

    name = models.CharField(
        max_length=50,
        unique=True,
        help_text="Class name (e.g., 'Warrior', 'Scholar', 'Noble')",
    )
    description = models.TextField(
        default="",
        help_text="Description of what this class represents and its role",
    )
    is_hidden = models.BooleanField(
        default=False,
        help_text="Whether this class is hidden from normal class selection",
    )
    minimum_level = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(0), MaxValueValidator(10)],
        help_text="Minimum level required to have this class (0-10)",
    )

    # Many-to-many relationship with traits for core class traits
    core_traits = models.ManyToManyField(
        "traits.Trait",
        blank=True,
        related_name="classes_requiring_trait",
        help_text="Core traits associated with this class",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        ordering = ["minimum_level", "name"]
        indexes = [
            models.Index(fields=["is_hidden"]),
            models.Index(fields=["minimum_level"]),
        ]

    def __str__(self):
        return f"{self.name} (min level {self.minimum_level})"


class CharacterClassLevel(SharedMemoryModel):
    """
    Links characters to their classes with level tracking.

    Represents a character's assignment to a specific class at a specific level.
    Characters can have multiple classes at different levels.
    """

    character = models.ForeignKey(
        "objects.ObjectDB",
        on_delete=models.CASCADE,
        related_name="character_class_levels",
    )
    character_class = models.ForeignKey(
        CharacterClass,
        on_delete=models.CASCADE,
        related_name="character_assignments",
    )
    level = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        help_text="Current level in this class (1-10)",
    )
    is_primary = models.BooleanField(
        default=False,
        help_text="Whether this is the character's primary class",
    )

    class Meta:
        unique_together = ["character", "character_class"]
        ordering = ["character", "-is_primary", "-level", "character_class__name"]
        indexes = [
            models.Index(fields=["character"]),
            models.Index(fields=["character", "level"]),
            models.Index(fields=["character", "is_primary"]),
        ]

    def __str__(self):
        primary_marker = " (Primary)" if self.is_primary else ""
        return (
            f"{self.character.key}: {self.character_class.name} "
            f"(level {self.level}){primary_marker}"
        )

    @property
    def is_elite_eligible(self):
        """Check if character is at level 6+ and eligible for elite class graduation."""
        ELITE_ELIGIBILITY_LEVEL = 6
        return self.level >= ELITE_ELIGIBILITY_LEVEL


class Aspect(NaturalKeyMixin, SharedMemoryModel):
    """
    Broad character archetype that provides bonuses to matching checks.

    Players see aspect names as flavor; weights are staff-only mechanical values.
    Examples: Warfare, Subterfuge, Diplomacy, Scholarship.
    """

    name = models.CharField(
        max_length=50,
        unique=True,
        help_text="Aspect name (e.g., 'Warfare', 'Subterfuge')",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of what this aspect represents",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        ordering = ["name"]
        verbose_name = "Aspect"
        verbose_name_plural = "Aspects"

    def __str__(self):
        return self.name


class PathAspect(SharedMemoryModel):
    """
    Links a path to an aspect with a strength value.

    The weight determines how much bonus the path provides for checks
    tagged with this aspect. Higher weight = stronger bonus.
    """

    character_path = models.ForeignKey(
        Path,
        on_delete=models.CASCADE,
        related_name="path_aspects",
        help_text="The path this aspect belongs to",
    )
    aspect = models.ForeignKey(
        Aspect,
        on_delete=models.CASCADE,
        related_name="path_aspects",
        help_text="The aspect being granted",
    )
    weight = models.PositiveSmallIntegerField(
        default=1,
        help_text="Multiplier for this aspect (staff-only, not shown to players)",
    )

    class Meta:
        unique_together = ["character_path", "aspect"]
        verbose_name = "Path Aspect"
        verbose_name_plural = "Path Aspects"

    def __str__(self):
        return f"{self.character_path.name}: {self.aspect.name} (weight {self.weight})"
