"""
Species models for character species/race definitions.

This module contains:
- Species: Core species/subspecies with optional parent hierarchy
- Language: Languages available in the game
- SpeciesArea: Through model for Species + StartingArea M2M with all configuration
- SpeciesAreaStatBonus: Stat modifiers per species-area combination
"""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.traits.constants import PrimaryStat


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
        ordering = ["sort_order", "name"]

    def __str__(self):
        if self.parent:
            return f"{self.name} ({self.parent.name})"
        return self.name

    @property
    def is_subspecies(self) -> bool:
        """Return True if this species has a parent."""
        return self.parent_id is not None

    def get_ancestors(self) -> list["Species"]:
        """Return list of ancestors from immediate parent to root."""
        ancestors = []
        current = self.parent
        while current is not None:
            ancestors.append(current)
            current = current.parent
        return ancestors


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
        ordering = ["name"]

    def __str__(self):
        return self.name


class SpeciesArea(SharedMemoryModel):
    """
    Through model for Species + StartingArea many-to-many relationship.

    This is the central configuration point where Rex'alfar-from-Arx differs
    from Rex'alfar-from-Lenosia. All access control and customization happens here.

    Accessible from both directions:
    - species.area_options.all() - All areas this species is available in
    - starting_area.species_options.all() - All species available in this area
    """

    species = models.ForeignKey(
        Species,
        on_delete=models.CASCADE,
        related_name="area_options",
        help_text="The species",
    )
    starting_area = models.ForeignKey(
        "character_creation.StartingArea",
        on_delete=models.CASCADE,
        related_name="species_options",
        help_text="The starting area",
    )

    # Access Control
    trust_required = models.PositiveIntegerField(
        default=0,
        help_text="Minimum trust level required (0 = all players)",
    )
    is_available = models.BooleanField(
        default=True,
        help_text="Staff toggle to enable/disable this option",
    )

    # Costs & Display
    cg_point_cost = models.IntegerField(
        default=0,
        help_text="CG point cost for selecting this species-area combination",
    )
    description_override = models.TextField(
        blank=True,
        help_text="Area-specific description (overrides species.description if set)",
    )
    sort_order = models.PositiveIntegerField(
        default=0,
        help_text="Display order in selection UI (lower = first)",
    )

    # Starting Languages (simple M2M - starting languages are always full fluency)
    starting_languages = models.ManyToManyField(
        Language,
        blank=True,
        related_name="species_area_options",
        help_text="Languages characters start with (full fluency)",
    )

    class Meta:
        verbose_name = "Species Area Option"
        verbose_name_plural = "Species Area Options"
        unique_together = [["species", "starting_area"]]
        ordering = ["starting_area__name", "sort_order", "species__name"]

    def __str__(self):
        return f"{self.species.name} ({self.starting_area.name})"

    @property
    def display_description(self) -> str:
        """Return area-specific description or fall back to species description."""
        return self.description_override or self.species.description

    def is_accessible_by(self, account) -> bool:
        """
        Check if an account can select this species-area option.

        Args:
            account: The account to check access for

        Returns:
            True if the account can select this option
        """
        if not self.is_available:
            return False

        # Staff bypass all restrictions
        if account.is_staff:
            return True

        # Check trust requirement
        if self.trust_required > 0:
            try:
                account_trust = account.trust
            except AttributeError:
                # Trust system not yet implemented, allow if trust_required is 0
                return self.trust_required == 0
            return account_trust >= self.trust_required

        return True

    def get_stat_bonuses_dict(self) -> dict[str, int]:
        """
        Return stat bonuses as a dictionary.

        Returns:
            Dict mapping stat names to bonus values, e.g., {"strength": 1, "agility": -1}
        """
        return {bonus.stat: bonus.value for bonus in self.stat_bonuses.all()}


class SpeciesAreaStatBonus(models.Model):
    """
    Individual stat modifier for a species-area combination.

    Example: Rex'alfar from Arx might have:
    - SpeciesAreaStatBonus(stat="agility", value=1)
    - SpeciesAreaStatBonus(stat="strength", value=-1)
    """

    species_area = models.ForeignKey(
        SpeciesArea,
        on_delete=models.CASCADE,
        related_name="stat_bonuses",
        help_text="The species-area combination this bonus applies to",
    )
    stat = models.CharField(
        max_length=20,
        choices=PrimaryStat.choices,
        help_text="The stat to modify",
    )
    value = models.SmallIntegerField(
        help_text="Bonus value (+1, -1, +2, etc.)",
    )

    class Meta:
        verbose_name = "Species Area Stat Bonus"
        verbose_name_plural = "Species Area Stat Bonuses"
        unique_together = [["species_area", "stat"]]

    def __str__(self):
        sign = "+" if self.value >= 0 else ""
        return f"{self.species_area}: {sign}{self.value} {self.get_stat_display()}"
