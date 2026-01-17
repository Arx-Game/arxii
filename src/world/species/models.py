"""
Species models for character species/race definitions.

This module contains:
- Species: Core species/subspecies with optional parent hierarchy
- Language: Languages available in the game
- SpeciesOrigin: Cultural/regional variants with stat bonuses (permanent character data)
- SpeciesOriginStatBonus: Stat modifiers for species origins
"""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.traits.constants import PrimaryStat


class SpeciesManager(models.Manager["Species"]):
    """Manager for Species model with natural key support."""

    def get_by_natural_key(self, name: str) -> "Species":
        return self.get(name=name)


class Species(SharedMemoryModel):
    """
    Core species/subspecies definition with optional parent hierarchy.

    Examples:
    - Human (parent=null) - directly playable
    - Elven (parent=null) - category only if no SpeciesOrigin records
    - Rex'alfar (parent=Elven) - playable subspecies
    - Nox'alfar (parent=Elven) - playable subspecies

    Access control is handled in SpeciesOption (character_creation app). This model
    is pure data about what species exist in the game world.
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

    objects = SpeciesManager()

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

    def natural_key(self) -> tuple[str]:
        return (self.name,)


class LanguageManager(models.Manager["Language"]):
    """Manager for Language model with natural key support."""

    def get_by_natural_key(self, name: str) -> "Language":
        return self.get(name=name)


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

    objects = LanguageManager()

    class Meta:
        verbose_name = "Language"
        verbose_name_plural = "Languages"

    def __str__(self):
        return self.name

    def natural_key(self) -> tuple[str]:
        return (self.name,)


class SpeciesOriginManager(models.Manager["SpeciesOrigin"]):
    """Manager for SpeciesOrigin model with natural key support."""

    def get_by_natural_key(self, species_name: str, name: str) -> "SpeciesOrigin":
        return self.get(species__name=species_name, name=name)


class SpeciesOrigin(SharedMemoryModel):
    """
    A cultural/regional variant of a species with permanent character data.

    This represents what a species variant is like - their stat bonuses,
    cultural traits, and description. This is lore data that becomes
    permanent character data, not CG-specific mechanics.

    Examples:
    - "Compact Rex'alfar" - Rex'alfar from the Compact with specific bonuses
    - "Wastes Thornweir" - Thornweir adapted to the Wastes environment
    - "Arvani Human" - Humans from Arx with city-dweller traits

    The same SpeciesOrigin can be made available in multiple StartingAreas
    via SpeciesOption in the character_creation app.
    """

    species = models.ForeignKey(
        Species,
        on_delete=models.CASCADE,
        related_name="origins",
        help_text="The species this origin belongs to (can be a sub-species)",
    )
    name = models.CharField(
        max_length=100,
        help_text="Name for this origin (e.g., 'Compact Rex'alfar', 'Arvani Human')",
    )
    description = models.TextField(
        blank=True,
        help_text="Lore description of this species origin",
    )

    objects = SpeciesOriginManager()

    class Meta:
        verbose_name = "Species Origin"
        verbose_name_plural = "Species Origins"
        unique_together = [["species", "name"]]

    def __str__(self):
        return f"{self.name} ({self.species.name})"

    def natural_key(self) -> tuple[str, str]:
        return (self.species.name, self.name)

    natural_key.dependencies = ["species.Species"]  # type: ignore[attr-defined]

    def get_stat_bonuses_dict(self) -> dict[str, int]:
        """
        Return stat bonuses as a dictionary.

        Returns:
            Dict mapping stat names to bonus values, e.g., {"strength": 1, "agility": -1}
        """
        return {bonus.stat: bonus.value for bonus in self.stat_bonuses.all()}


class SpeciesOriginStatBonusManager(models.Manager["SpeciesOriginStatBonus"]):
    """Manager for SpeciesOriginStatBonus model with natural key support."""

    def get_by_natural_key(
        self, species_name: str, origin_name: str, stat: str
    ) -> "SpeciesOriginStatBonus":
        return self.get(
            species_origin__species__name=species_name,
            species_origin__name=origin_name,
            stat=stat,
        )


class SpeciesOriginStatBonus(models.Model):
    """
    Individual stat modifier for a species origin.

    These are permanent character data - the stat bonuses apply to the character
    forever, not just during character creation.

    Example: Compact Rex'alfar might have:
    - SpeciesOriginStatBonus(stat="agility", value=1)
    - SpeciesOriginStatBonus(stat="strength", value=-1)
    """

    species_origin = models.ForeignKey(
        SpeciesOrigin,
        on_delete=models.CASCADE,
        related_name="stat_bonuses",
        help_text="The species origin this bonus applies to",
    )
    stat = models.CharField(
        max_length=20,
        choices=PrimaryStat.choices,
        help_text="The stat to modify",
    )
    value = models.SmallIntegerField(
        help_text="Bonus value (+1, -1, +2, etc.)",
    )

    objects = SpeciesOriginStatBonusManager()

    class Meta:
        verbose_name = "Species Origin Stat Bonus"
        verbose_name_plural = "Species Origin Stat Bonuses"
        unique_together = [["species_origin", "stat"]]

    def __str__(self):
        sign = "+" if self.value >= 0 else ""
        return f"{self.species_origin.name}: {sign}{self.value} {self.get_stat_display()}"

    def natural_key(self) -> tuple[str, str, str]:
        return (self.species_origin.species.name, self.species_origin.name, self.stat)

    natural_key.dependencies = ["species.SpeciesOrigin"]  # type: ignore[attr-defined]
