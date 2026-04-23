"""Affinity and Resonance domain models.

Affinities are the three magical sources (Celestial, Primal, Abyssal).
Resonances are style tags that contribute to affinities and have opposing pairs.
Both are proper domain models replacing the old ModifierTarget-based pattern.
"""

from functools import cached_property

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin


class AffinityManager(NaturalKeyManager):
    """Manager for Affinity with natural key support."""


class Affinity(NaturalKeyMixin, SharedMemoryModel):
    """
    A magical affinity (Celestial, Abyssal, Primal).

    Proper domain model replacing the old pattern of storing affinities
    as ModifierTarget rows with category='affinity'.
    """

    name = models.CharField(
        max_length=50,
        unique=True,
        help_text="Affinity name (e.g., 'Celestial', 'Abyssal', 'Primal').",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of this affinity.",
    )
    objects = AffinityManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        verbose_name_plural = "Affinities"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class ResonanceManager(NaturalKeyManager):
    """Manager for Resonance with natural key support."""


class Resonance(NaturalKeyMixin, SharedMemoryModel):
    """
    A magical resonance — a style tag that defines magical identity.

    Resonances contribute to affinities and have opposing pairs.
    Proper domain model replacing the old pattern of storing resonances
    as ModifierTarget rows with category='resonance'.
    """

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Resonance name (e.g., 'Bene', 'Praedari', 'Sylva').",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of this resonance.",
    )
    affinity = models.ForeignKey(
        Affinity,
        on_delete=models.PROTECT,
        related_name="resonances",
        help_text="Which affinity this resonance contributes to.",
    )
    opposite = models.OneToOneField(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="opposite_of",
        help_text="The opposing resonance in the pair.",
    )
    properties = models.ManyToManyField(
        "mechanics.Property",
        blank=True,
        related_name="resonances",
        help_text="Properties associated with this resonance (e.g., Flame → flame property).",
    )
    objects = ResonanceManager()

    @cached_property
    def cached_properties(self) -> list:
        """Fallback for when prefetch is not used. Prefer prefetch_related with to_attr."""
        return list(self.properties.all())

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        ordering = ["affinity", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.affinity.name})"
