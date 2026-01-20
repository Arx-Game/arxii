"""
Magic system models.

This module contains the foundational models for the magic system:
- Affinity: The three magical affinities (Celestial, Primal, Abyssal)
- Resonance: Style tags that define magical identity
- CharacterAura: Tracks a character's affinity percentages
- ResonanceAttachment models: Link resonances to various game objects
"""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.magic.types import AffinityType


class AffinityManager(NaturalKeyManager):
    """Manager for Affinity with natural key support."""


class Affinity(NaturalKeyMixin, SharedMemoryModel):
    """
    One of the three magical affinities: Celestial, Primal, or Abyssal.

    These are lookup/configuration records, not per-character data.
    Use SharedMemoryModel for caching since these rarely change.
    """

    affinity_type = models.CharField(
        max_length=20,
        choices=AffinityType.choices,
        unique=True,
        help_text="The affinity type identifier.",
    )
    name = models.CharField(
        max_length=50,
        help_text="Display name for this affinity.",
    )
    description = models.TextField(
        blank=True,
        help_text="Player-facing description of this affinity.",
    )
    admin_notes = models.TextField(
        blank=True,
        help_text="Staff-only notes about this affinity's mechanics.",
    )

    objects = AffinityManager()

    class Meta:
        verbose_name_plural = "Affinities"

    class NaturalKeyConfig:
        fields = ["affinity_type"]

    def __str__(self) -> str:
        return self.name


class ResonanceManager(NaturalKeyManager):
    """Manager for Resonance with natural key support."""


class Resonance(NaturalKeyMixin, SharedMemoryModel):
    """
    A style tag that defines magical identity.

    Resonances like Shadows, Majesty, Steel, Allure define the themes
    that make a character who they are. When appearance, equipment,
    environment, and powers align with resonances, magic amplifies.
    """

    name = models.CharField(
        max_length=50,
        help_text="Display name for this resonance.",
    )
    slug = models.SlugField(
        max_length=50,
        unique=True,
        help_text="URL-safe identifier for this resonance.",
    )
    default_affinity = models.ForeignKey(
        Affinity,
        on_delete=models.PROTECT,
        related_name="resonances",
        help_text="The default affinity leaning for this resonance.",
    )
    description = models.TextField(
        blank=True,
        help_text="Player-facing description of this resonance.",
    )
    admin_notes = models.TextField(
        blank=True,
        help_text="Staff-only notes about this resonance.",
    )

    objects = ResonanceManager()

    class Meta:
        ordering = ["name"]

    class NaturalKeyConfig:
        fields = ["slug"]
        dependencies = ["world.magic.Affinity"]

    def __str__(self) -> str:
        return self.name
