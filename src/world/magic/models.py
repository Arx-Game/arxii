"""
Magic system models.

This module contains the foundational models for the magic system:
- Affinity: The three magical affinities (Celestial, Primal, Abyssal)
- Resonance: Style tags that define magical identity
- CharacterAura: Tracks a character's affinity percentages
- ResonanceAttachment models: Link resonances to various game objects
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from evennia.objects.models import ObjectDB
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.magic.types import AffinityType, ResonanceScope, ResonanceStrength


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


class CharacterAura(models.Model):
    """
    Tracks a character's soul-state across the three affinities.

    Aura is stored as percentages (0-100) that should sum to 100.
    Player-facing display uses narrative descriptions, not raw numbers.
    """

    character = models.OneToOneField(
        ObjectDB,
        on_delete=models.CASCADE,
        related_name="aura",
        help_text="The character this aura belongs to.",
    )
    celestial = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal(0)), MaxValueValidator(Decimal(100))],
        help_text="Percentage of Celestial affinity (0-100).",
    )
    primal = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("80.00"),
        validators=[MinValueValidator(Decimal(0)), MaxValueValidator(Decimal(100))],
        help_text="Percentage of Primal affinity (0-100).",
    )
    abyssal = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("20.00"),
        validators=[MinValueValidator(Decimal(0)), MaxValueValidator(Decimal(100))],
        help_text="Percentage of Abyssal affinity (0-100).",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Character Aura"
        verbose_name_plural = "Character Auras"

    def __str__(self) -> str:
        return f"Aura of {self.character}"

    def clean(self) -> None:
        """Validate that percentages sum to 100."""
        total = self.celestial + self.primal + self.abyssal
        if total != Decimal("100.00"):
            msg = f"Aura percentages must sum to 100, got {total}."
            raise ValidationError(msg)

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def dominant_affinity(self) -> AffinityType:
        """Return the affinity type with the highest percentage."""
        values = [
            (self.celestial, AffinityType.CELESTIAL),
            (self.primal, AffinityType.PRIMAL),
            (self.abyssal, AffinityType.ABYSSAL),
        ]
        return max(values, key=lambda x: x[0])[1]


class CharacterResonance(models.Model):
    """
    A resonance attached to a character.

    Personal resonances come from heritage, personality, or development.
    They stack with resonances from equipment, environment, and powers.
    """

    character = models.ForeignKey(
        ObjectDB,
        on_delete=models.CASCADE,
        related_name="resonances",
        help_text="The character this resonance is attached to.",
    )
    resonance = models.ForeignKey(
        Resonance,
        on_delete=models.PROTECT,
        related_name="character_attachments",
        help_text="The resonance type.",
    )
    scope = models.CharField(
        max_length=20,
        choices=ResonanceScope.choices,
        default=ResonanceScope.SELF,
        help_text="Whether this resonance affects only the character or an area.",
    )
    strength = models.CharField(
        max_length=20,
        choices=ResonanceStrength.choices,
        default=ResonanceStrength.MODERATE,
        help_text="The strength of this resonance attachment.",
    )
    flavor_text = models.TextField(
        blank=True,
        help_text="Optional player-defined description of how this resonance manifests.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this resonance is currently active.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["character", "resonance"]
        verbose_name = "Character Resonance"
        verbose_name_plural = "Character Resonances"

    def __str__(self) -> str:
        return f"{self.resonance} on {self.character}"
