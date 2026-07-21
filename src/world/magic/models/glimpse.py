"""Glimpse tag catalog + per-character picks (#2427).

The Glimpse is the narrative of a character's first magical awakening
(prose lives on ``CharacterAura.glimpse_story``). This module adds the
guided, tag-driven layer: an authored tag catalog across four narrative
axes, the character's chosen tags, and curated tag→distinction
suggestions. Catalog rows are lore-repo content (``CONTENT_MODELS``);
``CharacterGlimpseTag`` is instance data and never exported.

All writes go through ``world.magic.services.glimpse`` so
``CharacterAura.glimpse_state`` stays consistent.
"""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.magic.constants import GlimpseTagAxis


class GlimpseTagManager(NaturalKeyManager):
    """Manager for GlimpseTag with natural key support."""


class GlimpseTag(NaturalKeyMixin, SharedMemoryModel):
    """One authored choice in the guided glimpse flow (#2427).

    Content model — authored in the lore repo, exported/imported via
    ``CONTENT_MODELS``. No factory-seeded catalog.
    """

    axis = models.CharField(
        max_length=20,
        choices=GlimpseTagAxis.choices,
        help_text="Which guided step this tag belongs to.",
    )
    name = models.CharField(max_length=100, help_text="Player-facing tag name.")
    slug = models.SlugField(max_length=100, unique=True, help_text="Natural key.")
    description = models.TextField(
        blank=True, help_text="What choosing this tag says about the glimpse."
    )
    example = models.TextField(
        blank=True,
        help_text="Short illustrative sentence shown in the guided step.",
    )
    sort_order = models.PositiveIntegerField(default=0, help_text="Display order within the axis.")
    is_active = models.BooleanField(
        default=True, help_text="Inactive tags are hidden from the CG flow."
    )
    paths = models.ManyToManyField(
        "classes.Path",
        blank=True,
        related_name="glimpse_trigger_tags",
        help_text="Restricts this tag to these paths. Empty = available to all paths.",
    )

    objects = GlimpseTagManager()

    class Meta:
        verbose_name = "Glimpse Tag"
        verbose_name_plural = "Glimpse Tags"
        ordering = ["axis", "sort_order", "name"]

    class NaturalKeyConfig:
        fields = ["slug"]

    def __str__(self) -> str:
        return f"{self.get_axis_display()}: {self.name}"


class CharacterGlimpseTag(SharedMemoryModel):
    """A character's chosen glimpse tag (#2427). Instance data — never exported."""

    aura = models.ForeignKey(
        "magic.CharacterAura",
        on_delete=models.CASCADE,
        related_name="glimpse_tags",
        help_text="The aura (one per character) whose Glimpse this tag describes.",
    )
    tag = models.ForeignKey(
        GlimpseTag,
        on_delete=models.PROTECT,
        related_name="character_rows",
        help_text="The chosen catalog tag.",
    )

    class Meta:
        verbose_name = "Character Glimpse Tag"
        verbose_name_plural = "Character Glimpse Tags"
        unique_together = [["aura", "tag"]]
        ordering = ["tag__axis", "tag__sort_order"]

    def __str__(self) -> str:
        return f"{self.tag} on {self.aura.character}"


class GlimpseTagDistinctionSuggestionManager(NaturalKeyManager):
    """Manager for GlimpseTagDistinctionSuggestion with natural key support."""


class GlimpseTagDistinctionSuggestion(NaturalKeyMixin, SharedMemoryModel):
    """Curated tag→distinction suggestion (#2427). Content model (lore repo).

    Purely a suggestion surface for the CG flow's "distinctions born of this
    moment" panel — grants nothing. FK direction per ADR-0010: glimpse-domain
    content points *into* the reusable ``Distinction`` primitive so
    ``distinctions`` stays dependency-free.
    """

    tag = models.ForeignKey(
        GlimpseTag,
        on_delete=models.CASCADE,
        related_name="distinction_suggestions",
        help_text="The glimpse tag that suggests the distinction.",
    )
    distinction = models.ForeignKey(
        "distinctions.Distinction",
        on_delete=models.CASCADE,
        related_name="glimpse_tag_suggestions",
        help_text="The distinction this tag suggests considering.",
    )
    sort_order = models.PositiveIntegerField(
        default=0, help_text="Display order within the tag's suggestions."
    )

    objects = GlimpseTagDistinctionSuggestionManager()

    class Meta:
        verbose_name = "Glimpse Tag Distinction Suggestion"
        verbose_name_plural = "Glimpse Tag Distinction Suggestions"
        unique_together = [["tag", "distinction"]]
        ordering = ["tag__axis", "tag__sort_order", "sort_order"]

    class NaturalKeyConfig:
        fields = ["tag", "distinction"]
        dependencies = ["magic.GlimpseTag", "distinctions.Distinction"]

    def __str__(self) -> str:
        return f"{self.tag.name} → {self.distinction.name}"
