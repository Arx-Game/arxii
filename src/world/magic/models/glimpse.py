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

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, ClassVar

from django.db import models
from django.utils.functional import cached_property
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from evennia_extensions.handlers import CachedRowsHandler
from evennia_extensions.mixins import CachedPropertiesMixin
from world.contributors.models import CreditedContent
from world.magic.constants import GlimpseTagAxis

if TYPE_CHECKING:
    from world.character_creation.models import DistinctionOffer


class GlimpseTagOffersHandler(CachedRowsHandler["DistinctionOffer"]):
    """The distinctions one glimpse tag opens, in display order (#3675, ADR-0278).

    ``DistinctionOffer`` lives in ``world.character_creation.models``, which the
    magic app must not import at module scope (ADR-0010: magic is the
    general/foundational side, mirroring ``services/tradition_membership.py``'s
    lazy imports) - both ``load()`` and ``rows_for()`` import it lazily.
    """

    attname: ClassVar[str] = "offers"

    def load(self) -> list[DistinctionOffer]:
        from world.character_creation.models import DistinctionOffer  # noqa: PLC0415

        return list(
            DistinctionOffer.objects.filter(glimpse_tag_id=self.parent.pk, is_active=True)
            .select_related("distinction")
            .order_by("sort_order", "id")
        )

    @classmethod
    def rows_for(cls, parents: list[models.Model]) -> dict[int, list[DistinctionOffer]]:
        """One query for every offer across ``parents``, bucketed by glimpse tag."""
        from world.character_creation.models import DistinctionOffer  # noqa: PLC0415

        grouped: dict[int, list[DistinctionOffer]] = defaultdict(list)
        rows = (
            DistinctionOffer.objects.filter(
                glimpse_tag_id__in=[parent.pk for parent in parents], is_active=True
            )
            .select_related("distinction")
            .order_by("sort_order", "id")
        )
        for offer in rows:
            grouped[offer.glimpse_tag_id].append(offer)
        return grouped


class GlimpseTagManager(NaturalKeyManager):
    """Manager for GlimpseTag with natural key support."""


class GlimpseTag(CachedPropertiesMixin, NaturalKeyMixin, CreditedContent, SharedMemoryModel):
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
        "arxii.Path",
        blank=True,
        related_name="glimpse_trigger_tags",
        help_text="Restricts this tag to these paths. Empty = available to all paths.",
    )
    affinity = models.ForeignKey(
        "arxii.Affinity",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="glimpse_tags",
        help_text=(
            "Affinity this tag nudges at CG finalize. Set on TONE and TRIGGER "
            "tags to apply a small aura adjustment. Null = no affinity nudge."
        ),
    )

    objects = GlimpseTagManager()

    class Meta:
        verbose_name = "Glimpse Tag"
        verbose_name_plural = "Glimpse Tags"
        ordering = ["axis", "sort_order", "name"]

    class NaturalKeyConfig:
        fields = ["slug"]

    @cached_property
    def offers(self) -> GlimpseTagOffersHandler:
        """This tag's active distinction offers. Cleared by any offer save/delete
        through ``DistinctionOffer.related_cache_fields`` (ADR-0278)."""
        return GlimpseTagOffersHandler(self)

    def __str__(self) -> str:
        return f"{self.get_axis_display()}: {self.name}"


class CharacterGlimpseTag(SharedMemoryModel):
    """A character's chosen glimpse tag (#2427). Instance data — never exported."""

    aura = models.ForeignKey(
        "arxii.CharacterAura",
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
