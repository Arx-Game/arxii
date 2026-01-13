"""
Species models for character species/race definitions.

This module contains:
- Species: Core species/subspecies with optional parent hierarchy
- Language: Languages available in the game

Note: SpeciesArea and SpeciesAreaStatBonus are in character_creation app
since they're only used during character creation.
"""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel


class Species(SharedMemoryModel):
    """
    Core species/subspecies definition with optional parent hierarchy.

    Examples:
    - Human (parent=null) - directly playable
    - Elven (parent=null) - category only if no SpeciesArea records
    - Rex'alfar (parent=Elven) - playable subspecies
    - Nox'alfar (parent=Elven) - playable subspecies

    Access control is handled in SpeciesArea, not here. This model is pure data
    about what species exist in the game world.
    """

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Species name (e.g., 'Human', 'Rex'alfar', 'Nox'alfar')",
    )
    description = models.TextField(
        blank=True,
        help_text="Base lore/description of this species",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
        help_text="Parent species for subspecies (e.g., Rex'alfar.parent = Elven)",
    )
    sort_order = models.PositiveIntegerField(
        default=0,
        help_text="Display ordering within parent grouping",
    )

    class Meta:
        verbose_name = "Species"
        verbose_name_plural = "Species"

    def __str__(self):
        if self.parent:
            return f"{self.name} ({self.parent.name})"
        return self.name

    @property
    def is_subspecies(self) -> bool:
        """Return True if this species has a parent."""
        return self.parent_id is not None


class Language(SharedMemoryModel):
    """
    Languages available in the game.

    Used for starting languages in character creation and language skills.
    """

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Language name (e.g., 'Common', 'Elvish', 'Arvani')",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of this language",
    )

    class Meta:
        verbose_name = "Language"
        verbose_name_plural = "Languages"

    def __str__(self):
        return self.name
