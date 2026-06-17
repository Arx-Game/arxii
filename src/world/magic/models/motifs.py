"""Motifs: character-level magical aesthetic.

Facets are hierarchical imagery/symbolism (Category > Subcategory > Specific).
Motif is a character-level container; MotifResonance holds resonances (from
gifts or optional) and MotifResonanceAssociation links motif resonances to
facets.
"""

from django.core.exceptions import ValidationError
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.magic.models.affinity import Resonance


class FacetManager(NaturalKeyManager):
    """Manager for Facet with natural key support."""


class Facet(NaturalKeyMixin, SharedMemoryModel):
    """
    Hierarchical imagery/symbolism that players assign to resonances.

    Facets are organized in a tree: Category > Subcategory > Specific.
    Examples: Creatures > Mammals > Wolf
              Materials > Textiles > Silk

    Players assign facets to their resonances to define personal meaning.
    Items can have facets; matching facets boost resonances.
    """

    name = models.CharField(
        max_length=100,
        help_text="Facet name (e.g., 'Wolf', 'Silk', 'Creatures').",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
        help_text="Parent facet for hierarchy (null = top-level category).",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of this facet's thematic meaning.",
    )

    objects = FacetManager()

    class Meta:
        unique_together = ["parent", "name"]
        verbose_name = "Facet"
        verbose_name_plural = "Facets"

    class NaturalKeyConfig:
        fields = ["name", "parent"]
        dependencies = ["magic.Facet"]

    def __str__(self) -> str:
        if self.parent:
            return f"{self.name} ({self.parent.name})"
        return self.name

    @property
    def depth(self) -> int:
        """Return the depth in the hierarchy (0 = top-level)."""
        depth = 0
        current = self.parent
        while current:
            depth += 1
            current = current.parent
        return depth

    @property
    def full_path(self) -> str:
        """Return full hierarchy path as string."""
        parts = [self.name]
        current = self.parent
        while current:
            parts.insert(0, current.name)
            current = current.parent
        return " > ".join(parts)

    @property
    def is_category(self) -> bool:
        """Return True if this is a top-level category."""
        return self.parent is None


class Motif(SharedMemoryModel):
    """
    Character-level magical aesthetic.

    One Motif per character, shared across all Gifts. Contains resonances
    (auto-populated from Gifts + optional extras) and their associations.
    """

    character = models.OneToOneField(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="motif",
        help_text="The character this motif belongs to.",
    )
    description = models.TextField(
        blank=True,
        help_text="Overall magical aesthetic description.",
    )

    class Meta:
        verbose_name = "Motif"
        verbose_name_plural = "Motifs"

    def __str__(self) -> str:
        return f"Motif of {self.character}"


class MotifResonance(SharedMemoryModel):
    """
    A resonance attached to a character's motif.

    Some resonances are auto-populated from Gifts (is_from_gift=True),
    others are optional additions based on affinity skill.
    """

    motif = models.ForeignKey(
        Motif,
        on_delete=models.CASCADE,
        related_name="resonances",
        help_text="The motif this resonance belongs to.",
    )
    resonance = models.ForeignKey(
        Resonance,
        on_delete=models.PROTECT,
        related_name="motif_resonances",
        help_text="The resonance type.",
    )
    is_from_gift = models.BooleanField(
        default=False,
        help_text="True if auto-populated from a Gift, False if optional.",
    )

    class Meta:
        unique_together = ["motif", "resonance"]
        verbose_name = "Motif Resonance"
        verbose_name_plural = "Motif Resonances"

    def __str__(self) -> str:
        source = "(from gift)" if self.is_from_gift else "(optional)"
        return f"{self.resonance.name} on {self.motif} {source}"


class MotifResonanceLink(SharedMemoryModel):
    """Abstract base for models that cap the number of items linked to a MotifResonance.

    Subclasses declare:
    - A concrete ``motif_resonance`` FK (related_name differs per subclass).
    - ``MAX_PER_RESONANCE`` class attribute (int) — the cap.
    - ``CAP_ITEM_LABEL`` class attribute (str) — noun used in the error message.

    ``clean()`` counts existing sibling rows (excluding self) and raises
    ``ValidationError`` when the cap is reached. ``save()`` calls ``clean()``
    before persisting.
    """

    MAX_PER_RESONANCE: int  # required class attribute on each concrete subclass
    CAP_ITEM_LABEL: str = "items"  # overridden per subclass for user-facing message

    class Meta:
        abstract = True

    def clean(self) -> None:
        """Enforce the per-resonance cap."""
        if self.motif_resonance_id:  # type: ignore[attr-defined]
            current_count = (
                type(self)
                .objects.filter(motif_resonance=self.motif_resonance_id)  # type: ignore[attr-defined]
                .exclude(pk=self.pk)
                .count()
            )
            if current_count >= self.MAX_PER_RESONANCE:
                msg = f"Maximum {self.MAX_PER_RESONANCE} {self.CAP_ITEM_LABEL} per resonance."
                raise ValidationError(msg)

    def save(self, *args, **kwargs) -> None:
        self.clean()
        super().save(*args, **kwargs)


class MotifResonanceAssociation(MotifResonanceLink):
    """
    Links a motif resonance to a facet (hierarchical imagery/symbolism).

    Maximum 5 facets per motif resonance (enforced via MotifResonanceLink).
    """

    MAX_PER_RESONANCE = 5
    CAP_ITEM_LABEL = "facets"
    # Alias kept for any code that references the old constant name.
    MAX_FACETS_PER_RESONANCE = MAX_PER_RESONANCE

    motif_resonance = models.ForeignKey(
        MotifResonance,
        on_delete=models.CASCADE,
        related_name="facet_assignments",
        help_text="The motif resonance this facet belongs to.",
    )
    facet = models.ForeignKey(
        Facet,
        on_delete=models.PROTECT,
        related_name="motif_usages",
        help_text="The facet imagery.",
    )

    class Meta:
        unique_together = ["motif_resonance", "facet"]
        verbose_name = "Motif Resonance Association"
        verbose_name_plural = "Motif Resonance Associations"

    def __str__(self) -> str:
        return f"{self.facet.name} for {self.motif_resonance}"


class MotifResonanceStyle(MotifResonanceLink):
    """
    Binds a Style to a MotifResonance, expressing character individualization.

    Maximum 3 styles per motif resonance (enforced via MotifResonanceLink).
    Two characters may bind the same Style to their own resonances independently.
    """

    MAX_PER_RESONANCE = 3
    CAP_ITEM_LABEL = "styles"

    motif_resonance = models.ForeignKey(
        MotifResonance,
        on_delete=models.CASCADE,
        related_name="style_assignments",
        help_text="The motif resonance this style belongs to.",
    )
    style = models.ForeignKey(
        "items.Style",
        on_delete=models.PROTECT,
        related_name="motif_usages",
        help_text="The aesthetic style.",
    )

    class Meta:
        unique_together = ["motif_resonance", "style"]
        verbose_name = "Motif Resonance Style"
        verbose_name_plural = "Motif Resonance Styles"

    def __str__(self) -> str:
        return f"{self.style.name} for {self.motif_resonance}"
