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
