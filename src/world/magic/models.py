"""
Magic system models.

This module contains the foundational models for the magic system:
- Affinity: The three magical affinities (Celestial, Primal, Abyssal)
- Resonance: Style tags that define magical identity
- CharacterAura: Tracks a character's affinity percentages
- ResonanceAttachment models: Link resonances to various game objects
- Gift: Thematic collections of magical powers
- Power: Individual magical abilities with Intensity/Control
- IntensityTier: Configurable thresholds for power effects
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


# =============================================================================
# Phase 2: Gifts & Powers
# =============================================================================


class IntensityTier(SharedMemoryModel):
    """
    Configurable thresholds for power intensity effects.

    As effective Intensity increases, powers can reach tier thresholds
    that unlock dramatically stronger effects. Higher tiers require
    higher Control checks.
    """

    name = models.CharField(
        max_length=50,
        help_text="Display name for this tier (e.g., 'Base', 'Enhanced', 'Dramatic').",
    )
    threshold = models.PositiveIntegerField(
        unique=True,
        help_text="Minimum intensity required to reach this tier.",
    )
    control_modifier = models.IntegerField(
        default=0,
        help_text="Additional control required at this tier (can be negative).",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of what this tier enables.",
    )
    admin_notes = models.TextField(
        blank=True,
        help_text="Staff-only notes about this tier.",
    )

    class Meta:
        ordering = ["threshold"]
        verbose_name = "Intensity Tier"
        verbose_name_plural = "Intensity Tiers"

    def __str__(self) -> str:
        return f"{self.name} ({self.threshold}+)"


class GiftManager(NaturalKeyManager):
    """Manager for Gift with natural key support."""


class Gift(NaturalKeyMixin, SharedMemoryModel):
    """
    A thematic collection of magical powers.

    Gifts represent a character's supernatural portfolio - like "Shadow Majesty"
    for dark regal influence. Each Gift contains multiple Powers that unlock
    as the character levels.
    """

    name = models.CharField(
        max_length=100,
        help_text="Display name for this gift.",
    )
    slug = models.SlugField(
        max_length=100,
        unique=True,
        help_text="URL-safe identifier for this gift.",
    )
    affinity = models.ForeignKey(
        Affinity,
        on_delete=models.PROTECT,
        related_name="gifts",
        help_text="The primary affinity of this gift.",
    )
    description = models.TextField(
        blank=True,
        help_text="Player-facing description of this gift.",
    )
    admin_notes = models.TextField(
        blank=True,
        help_text="Staff-only notes about this gift.",
    )
    resonances = models.ManyToManyField(
        Resonance,
        blank=True,
        related_name="gifts",
        help_text="Resonances associated with this gift.",
    )
    level_requirement = models.PositiveIntegerField(
        default=1,
        help_text="Minimum character level to acquire this gift.",
    )

    objects = GiftManager()

    class Meta:
        ordering = ["name"]

    class NaturalKeyConfig:
        fields = ["slug"]
        dependencies = ["world.magic.Affinity"]

    def __str__(self) -> str:
        return self.name


class PowerManager(NaturalKeyManager):
    """Manager for Power with natural key support."""


class Power(NaturalKeyMixin, SharedMemoryModel):
    """
    An individual magical ability within a Gift.

    Powers have base Intensity and Control values. When cast, effective
    values are modified by Aura, Resonances, and other factors. Higher
    effective Intensity can reach tier thresholds for stronger effects.
    """

    name = models.CharField(
        max_length=100,
        help_text="Display name for this power.",
    )
    slug = models.SlugField(
        max_length=100,
        unique=True,
        help_text="URL-safe identifier for this power.",
    )
    gift = models.ForeignKey(
        Gift,
        on_delete=models.CASCADE,
        related_name="powers",
        help_text="The gift this power belongs to.",
    )
    affinity = models.ForeignKey(
        Affinity,
        on_delete=models.PROTECT,
        related_name="powers",
        help_text="The affinity of this power (may differ from gift).",
    )
    base_intensity = models.PositiveIntegerField(
        default=10,
        help_text="Base intensity value before modifiers.",
    )
    base_control = models.PositiveIntegerField(
        default=10,
        help_text="Base control value before modifiers.",
    )
    anima_cost = models.PositiveIntegerField(
        default=1,
        help_text="Anima cost to use this power.",
    )
    level_requirement = models.PositiveIntegerField(
        default=1,
        help_text="Minimum character level to unlock this power.",
    )
    description = models.TextField(
        blank=True,
        help_text="Player-facing description of this power's base effect.",
    )
    admin_notes = models.TextField(
        blank=True,
        help_text="Staff-only notes about this power.",
    )
    resonances = models.ManyToManyField(
        Resonance,
        blank=True,
        related_name="powers",
        help_text="Resonances that boost this power.",
    )

    objects = PowerManager()

    class Meta:
        ordering = ["gift", "level_requirement", "name"]

    class NaturalKeyConfig:
        fields = ["slug"]
        dependencies = ["world.magic.Gift", "world.magic.Affinity"]

    def __str__(self) -> str:
        return f"{self.name} ({self.gift})"


class CharacterGift(models.Model):
    """
    Links a character to a Gift they possess.

    Characters start with one Gift at creation and may acquire more
    through play, training, or dramatic transformation.
    """

    character = models.ForeignKey(
        ObjectDB,
        on_delete=models.CASCADE,
        related_name="gifts",
        help_text="The character who possesses this gift.",
    )
    gift = models.ForeignKey(
        Gift,
        on_delete=models.PROTECT,
        related_name="character_grants",
        help_text="The gift possessed.",
    )
    acquired_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this gift was acquired.",
    )
    notes = models.TextField(
        blank=True,
        help_text="Notes about how this gift was acquired or customized.",
    )

    class Meta:
        unique_together = ["character", "gift"]
        verbose_name = "Character Gift"
        verbose_name_plural = "Character Gifts"

    def __str__(self) -> str:
        return f"{self.gift} on {self.character}"


class CharacterPower(models.Model):
    """
    Links a character to a Power they have unlocked.

    Powers are unlocked when a character meets level requirements
    and possesses the parent Gift.
    """

    character = models.ForeignKey(
        ObjectDB,
        on_delete=models.CASCADE,
        related_name="powers",
        help_text="The character who has unlocked this power.",
    )
    power = models.ForeignKey(
        Power,
        on_delete=models.PROTECT,
        related_name="character_grants",
        help_text="The power unlocked.",
    )
    unlocked_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this power was unlocked.",
    )
    times_used = models.PositiveIntegerField(
        default=0,
        help_text="Number of times this power has been used.",
    )
    notes = models.TextField(
        blank=True,
        help_text="Notes about this power's use or customization.",
    )

    class Meta:
        unique_together = ["character", "power"]
        verbose_name = "Character Power"
        verbose_name_plural = "Character Powers"

    def __str__(self) -> str:
        return f"{self.power} on {self.character}"
