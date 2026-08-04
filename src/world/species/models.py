"""
Species models for character species/race definitions.

This module contains:
- Species: Core species/subspecies with optional parent hierarchy
- SpeciesStatBonus: Stat modifiers for species
- Language: Languages available in the game
"""

from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.functional import cached_property
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.traits.constants import PrimaryStat

if TYPE_CHECKING:
    from world.codex.models import CodexEntry


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
    codex_entry = models.ForeignKey(
        "arxii.CodexEntry",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="species",
        help_text="Lore entry this species is bound to, if any.",
    )
    # Age axes (#2756)
    eternal_youth = models.BooleanField(
        default=False,
        help_text=(
            "Elves, vampires, and similar: apparent age locks in the early 20s "
            "(CG caps the age input at 29), no Maturation Points are ever "
            "earned, and old-age decline never begins."
        ),
    )
    decline_start_age = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        default=60,
        help_text=(
            "Biological age at which old-age decline checks begin (PLACEHOLDER "
            "60 for humans). Null = this species never declines; forced null "
            "in effect when eternal_youth is set."
        ),
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

    @property
    def lineage(self) -> list["Species"]:
        """This species followed by every ancestor, nearest first.

        The chain is at most two deep in practice (a Khati kind under Khati, an
        elf line under Elf) and every row is served by the idmapper cache after
        the first read, so the walk is cheap enough to do inline.

        A ``parent`` cycle would be a data defect rather than a modelled state;
        the seen-set keeps it from hanging whatever produced it.
        """
        chain: list[Species] = []
        seen: set[int] = set()
        current: Species | None = self
        while current is not None and current.pk not in seen:
            seen.add(current.pk)
            chain.append(current)
            current = current.parent
        return chain

    @property
    def codex_entries(self) -> list["CodexEntry"]:
        """Every codex entry a character of this species is owed (#2880).

        The species tier is authored so that the umbrella entry (Khati, Elf,
        Infernal) carries what the kinds share and each kind entry carries the
        kind, which only works if a subspecies character receives both. Species
        with ``codex_entry`` still null — Saurian, pending design — drop out
        rather than contributing a None.
        """
        return [
            species.codex_entry for species in self.lineage if species.codex_entry_id is not None
        ]

    @cached_property
    def cached_stat_bonuses(self) -> list["SpeciesStatBonus"]:
        """
        Get stat bonuses with prefetch support.

        This cached_property serves as the target for Prefetch(..., to_attr=).
        When prefetched, Django populates this directly. When accessed without
        prefetch, falls back to a fresh query.

        To invalidate: del instance.cached_stat_bonuses
        """
        return list(self.stat_bonuses.all())

    def get_stat_bonuses_dict(self) -> dict[str, int]:
        """
        Return stat bonuses as a dictionary.

        Returns:
            Dict mapping stat names to bonus values, e.g., {"strength": 1, "agility": -1}
        """
        return {bonus.stat: bonus.value for bonus in self.cached_stat_bonuses}


class SpeciesStatBonus(NaturalKeyMixin, SharedMemoryModel):
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
        dependencies = ["arxii.Species"]

    class Meta:
        verbose_name = "Species Stat Bonus"
        verbose_name_plural = "Species Stat Bonuses"
        unique_together = [["species", "stat"]]

    def __str__(self):
        sign = "+" if self.value >= 0 else ""
        return f"{self.species.name}: {sign}{self.value} {self.get_stat_display()}"


class SpeciesGiftGrant(NaturalKeyMixin, SharedMemoryModel):
    """A Minor Gift (and optional drawback) a species grants its members (ADR-0050).

    FK direction specific→general (ADR-0010): the grant lives on the species side and
    points into world/magic, world/conditions, and world/distinctions; those apps
    never import species.
    """

    species = models.ForeignKey(
        Species,
        on_delete=models.CASCADE,
        related_name="gift_grants",
        help_text="The species (or subspecies) that grants this Minor Gift.",
    )
    gift = models.ForeignKey(
        "arxii.Gift",
        on_delete=models.PROTECT,
        related_name="species_grants",
        help_text="The Minor Gift granted. Must have kind=MINOR.",
    )
    drawback_condition = models.ForeignKey(
        "arxii.ConditionTemplate",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="species_gift_drawbacks",
        help_text="Optional drawback condition applied at finalize (frenzy/sunlight-vuln).",
    )
    benefit_condition = models.ForeignKey(
        "arxii.ConditionTemplate",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="species_gift_benefits",
        help_text="Optional permanent beneficial condition applied at finalize "
        "(e.g. a resist-check bonus condition).",
    )
    drawback_distinction = models.ForeignKey(
        "arxii.Distinction",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="species_gift_drawbacks",
        help_text="Optional forced drawback distinction applied at finalize "
        "(a social/reputation price, e.g. feared-and-distrusted).",
    )
    cg_point_cost = models.PositiveIntegerField(
        default=0,
        help_text="CG points charged for this grant (0 = free). Summed across a "
        "species' grants into the character-creation points breakdown.",
    )
    inheritable = models.BooleanField(
        default=True,
        help_text="Whether child species inherit this grant via the ancestor walk. "
        "False = this grant is species-specific and does not propagate to children.",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["species", "gift"]
        dependencies = ["arxii.Species", "arxii.Gift", "arxii.Distinction"]

    class Meta:
        verbose_name = "Species Gift Grant"
        verbose_name_plural = "Species Gift Grants"
        unique_together = [["species", "gift"]]
        ordering = ["species", "gift"]

    def __str__(self) -> str:
        return f"{self.species.name} → {self.gift.name}"

    def clean(self) -> None:
        super().clean()
        from world.magic.constants import GiftKind  # noqa: PLC0415

        if self.gift.kind != GiftKind.MINOR:
            raise ValidationError({"gift": "Species grants must reference a MINOR gift."})


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
