"""
Species models for character species/race definitions.

This module contains:
- Species: Core species/subspecies with optional parent hierarchy
- SpeciesStatBonus: Stat modifiers for species
- Language: Languages available in the game
"""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.traits.constants import PrimaryStat


class Species(NaturalKeyMixin, SharedMemoryModel):
    """
    Core species/subspecies definition with optional parent hierarchy.

    Examples:
    - Human (parent=null) - directly playable
    - Elven (parent=null) - category only, not directly playable
    - Rex'alfar (parent=Elven) - playable subspecies
    - Nox'alfar (parent=Elven) - playable subspecies

    Access control is handled via Beginnings.allowed_species (character_creation app).
    This model is pure data about what species exist in the game world.
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
    starting_languages = models.ManyToManyField(
        "Language",
        blank=True,
        related_name="native_species",
        help_text="Racial languages known by this species",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

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

    def get_stat_bonuses_dict(self) -> dict[str, int]:
        """
        Return stat bonuses as a dictionary.

        Returns:
            Dict mapping stat names to bonus values, e.g., {"strength": 1, "agility": -1}
        """
        return {bonus.stat: bonus.value for bonus in self.stat_bonuses.all()}


class SpeciesStatBonus(NaturalKeyMixin, models.Model):
    """
    Individual stat modifier for a species.

    These are permanent character data - the stat bonuses apply to the character
    forever, not just during character creation.

    Example: Infernal might have:
    - SpeciesStatBonus(stat="charm", value=-1)
    """

    species = models.ForeignKey(
        Species,
        on_delete=models.CASCADE,
        related_name="stat_bonuses",
        help_text="The species this bonus applies to",
    )
    stat = models.CharField(
        max_length=20,
        choices=PrimaryStat.choices,
        help_text="The stat to modify",
    )
    value = models.SmallIntegerField(
        help_text="Bonus value (+1, -1, +2, etc.)",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["species", "stat"]
        dependencies = ["species.Species"]

    class Meta:
        verbose_name = "Species Stat Bonus"
        verbose_name_plural = "Species Stat Bonuses"
        unique_together = [["species", "stat"]]

    def __str__(self):
        sign = "+" if self.value >= 0 else ""
        return f"{self.species.name}: {sign}{self.value} {self.get_stat_display()}"


class Language(NaturalKeyMixin, SharedMemoryModel):
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

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        verbose_name = "Language"
        verbose_name_plural = "Languages"

    def __str__(self):
        return self.name
