"""
Arx II Character Classes System Models

Models for character classes and class progression.
Following Arx II design principles:
- Data-driven configuration for class mechanics
- Support for elite classes that combine base classes
- Flexible trait requirements system
- Clean separation between class definitions and character assignments
"""

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel


class CharacterClass(SharedMemoryModel):
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
