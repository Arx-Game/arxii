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
- CharacterAnima: Magical resource tracking
- AnimaRitualType: Types of personalized recovery rituals
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from evennia.objects.models import ObjectDB
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.magic.types import (
    AffinityType,
    AnimaRitualCategory,
    ResonanceScope,
    ResonanceStrength,
)


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


class CharacterAnima(models.Model):
    """
    Tracks a character's magical energy resource.

    Anima is spent to fuel powers and recovers through personalized rituals.
    Current anima fluctuates during play; max anima may increase with level.
    """

    character = models.OneToOneField(
        ObjectDB,
        on_delete=models.CASCADE,
        related_name="anima",
        help_text="The character this anima belongs to.",
    )
    current = models.PositiveIntegerField(
        default=10,
        help_text="Current anima available.",
    )
    maximum = models.PositiveIntegerField(
        default=10,
        help_text="Maximum anima capacity.",
    )
    last_recovery = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When anima was last recovered through ritual.",
    )

    class Meta:
        verbose_name = "Character Anima"
        verbose_name_plural = "Character Anima"

    def __str__(self) -> str:
        return f"Anima of {self.character} ({self.current}/{self.maximum})"

    def clean(self) -> None:
        """Validate that current doesn't exceed maximum."""
        if self.current > self.maximum:
            msg = "Current anima cannot exceed maximum."
            raise ValidationError(msg)

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)


class AnimaRitualTypeManager(NaturalKeyManager):
    """Manager for AnimaRitualType with natural key support."""


class AnimaRitualType(NaturalKeyMixin, SharedMemoryModel):
    """
    A predefined type of anima recovery ritual.

    Ritual types define categories of recovery activities. Characters
    personalize these with their own descriptions and resonance flavors.
    """

    name = models.CharField(
        max_length=50,
        help_text="Display name for this ritual type.",
    )
    slug = models.SlugField(
        max_length=50,
        unique=True,
        help_text="URL-safe identifier for this ritual type.",
    )
    category = models.CharField(
        max_length=20,
        choices=AnimaRitualCategory.choices,
        help_text="The category of ritual activity.",
    )
    description = models.TextField(
        blank=True,
        help_text="Player-facing description of this ritual type.",
    )
    admin_notes = models.TextField(
        blank=True,
        help_text="Staff-only notes about this ritual type.",
    )
    base_recovery = models.PositiveIntegerField(
        default=5,
        help_text="Base anima recovered when performing this ritual.",
    )

    objects = AnimaRitualTypeManager()

    class Meta:
        ordering = ["category", "name"]
        verbose_name = "Anima Ritual Type"
        verbose_name_plural = "Anima Ritual Types"

    class NaturalKeyConfig:
        fields = ["slug"]

    def __str__(self) -> str:
        return self.name


class CharacterAnimaRitual(models.Model):
    """
    A character's personalized anima recovery ritual.

    Characters define their own rituals based on predefined types,
    adding personal flavor text that reflects their identity.
    """

    character = models.ForeignKey(
        ObjectDB,
        on_delete=models.CASCADE,
        related_name="anima_rituals",
        help_text="The character who performs this ritual.",
    )
    ritual_type = models.ForeignKey(
        AnimaRitualType,
        on_delete=models.PROTECT,
        related_name="character_rituals",
        help_text="The type of ritual.",
    )
    personal_description = models.TextField(
        help_text="How this character personally performs this ritual.",
    )
    is_primary = models.BooleanField(
        default=False,
        help_text="Whether this is the character's primary recovery method.",
    )
    times_performed = models.PositiveIntegerField(
        default=0,
        help_text="Number of times this ritual has been performed.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["character", "ritual_type"]
        verbose_name = "Character Anima Ritual"
        verbose_name_plural = "Character Anima Rituals"

    def __str__(self) -> str:
        return f"{self.ritual_type} ritual for {self.character}"


class ThreadTypeManager(NaturalKeyManager):
    """Manager for ThreadType with natural key support."""


class ThreadType(NaturalKeyMixin, SharedMemoryModel):
    """
    A type of magical relationship (Thread) that emerges from axis values.

    Thread types like Lover, Ally, Rival emerge when axis values reach
    certain thresholds. A thread can match multiple types simultaneously.
    """

    name = models.CharField(
        max_length=50,
        help_text="Display name for this thread type.",
    )
    slug = models.SlugField(
        max_length=50,
        unique=True,
        help_text="URL-safe identifier for this thread type.",
    )
    description = models.TextField(
        blank=True,
        help_text="Player-facing description of this thread type.",
    )
    admin_notes = models.TextField(
        blank=True,
        help_text="Staff-only notes about this thread type.",
    )
    # Axis thresholds - relationship qualifies if all non-null thresholds are met
    romantic_threshold = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Minimum romantic value to qualify (null = not required).",
    )
    trust_threshold = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Minimum trust value to qualify (null = not required).",
    )
    rivalry_threshold = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Minimum rivalry value to qualify (null = not required).",
    )
    protective_threshold = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Minimum protective value to qualify (null = not required).",
    )
    enmity_threshold = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Minimum enmity value to qualify (null = not required).",
    )
    # Resonance bonus when this type applies
    grants_resonance = models.ForeignKey(
        Resonance,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="thread_type_grants",
        help_text="Resonance granted by this thread type.",
    )

    objects = ThreadTypeManager()

    class Meta:
        ordering = ["name"]
        verbose_name = "Thread Type"
        verbose_name_plural = "Thread Types"

    class NaturalKeyConfig:
        fields = ["slug"]
        dependencies = ["world.magic.Resonance"]

    def __str__(self) -> str:
        return self.name


class Thread(models.Model):
    """
    A magical connection between two characters.

    Threads are the magical manifestation of relationships. They have
    values along multiple axes and can match multiple thread types.
    Threads provide resonance bonuses and affect Anima recovery.
    """

    initiator = models.ForeignKey(
        ObjectDB,
        on_delete=models.CASCADE,
        related_name="threads_initiated",
        help_text="The character who initiated this thread.",
    )
    receiver = models.ForeignKey(
        ObjectDB,
        on_delete=models.CASCADE,
        related_name="threads_received",
        help_text="The character who received this thread.",
    )
    # Axis values (0-100)
    romantic = models.PositiveIntegerField(
        default=0,
        validators=[MaxValueValidator(100)],
        help_text="Romantic intensity (0-100).",
    )
    trust = models.PositiveIntegerField(
        default=0,
        validators=[MaxValueValidator(100)],
        help_text="Trust and faith (0-100).",
    )
    rivalry = models.PositiveIntegerField(
        default=0,
        validators=[MaxValueValidator(100)],
        help_text="Competitive tension (0-100).",
    )
    protective = models.PositiveIntegerField(
        default=0,
        validators=[MaxValueValidator(100)],
        help_text="Protective instinct (0-100).",
    )
    enmity = models.PositiveIntegerField(
        default=0,
        validators=[MaxValueValidator(100)],
        help_text="Hatred and opposition (0-100).",
    )
    # Soul Tether - special Abyssal bond
    is_soul_tether = models.BooleanField(
        default=False,
        help_text="Whether this is an Abyssal Soul Tether (grants Control bonus).",
    )
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["initiator", "receiver"]
        verbose_name = "Thread"
        verbose_name_plural = "Threads"

    def __str__(self) -> str:
        return f"Thread: {self.initiator} — {self.receiver}"

    def clean(self) -> None:
        """Validate thread constraints."""
        if self.initiator_id == self.receiver_id:
            msg = "A character cannot have a thread with themselves."
            raise ValidationError(msg)

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def get_matching_types(self):
        """Return all ThreadTypes that this thread qualifies for."""
        return [
            thread_type
            for thread_type in ThreadType.objects.all()
            if self._matches_type(thread_type)
        ]

    def _matches_type(self, thread_type: ThreadType) -> bool:
        """Check if this thread meets a type's thresholds."""
        checks = [
            (thread_type.romantic_threshold, self.romantic),
            (thread_type.trust_threshold, self.trust),
            (thread_type.rivalry_threshold, self.rivalry),
            (thread_type.protective_threshold, self.protective),
            (thread_type.enmity_threshold, self.enmity),
        ]
        return all(threshold is None or value >= threshold for threshold, value in checks)


class ThreadJournal(models.Model):
    """
    An IC-visible record of a thread's evolution.

    Journal entries document significant moments in a relationship,
    visible to both characters. They provide narrative context for
    how threads have grown or changed.
    """

    thread = models.ForeignKey(
        Thread,
        on_delete=models.CASCADE,
        related_name="journal_entries",
        help_text="The thread this entry belongs to.",
    )
    author = models.ForeignKey(
        ObjectDB,
        on_delete=models.SET_NULL,
        null=True,
        related_name="thread_journal_entries",
        help_text="The character who wrote this entry.",
    )
    content = models.TextField(
        help_text="The journal entry content (IC description of the moment).",
    )
    # Optional axis changes recorded with this entry
    romantic_change = models.IntegerField(
        default=0,
        help_text="Change in romantic value when this entry was made.",
    )
    trust_change = models.IntegerField(
        default=0,
        help_text="Change in trust value when this entry was made.",
    )
    rivalry_change = models.IntegerField(
        default=0,
        help_text="Change in rivalry value when this entry was made.",
    )
    protective_change = models.IntegerField(
        default=0,
        help_text="Change in protective value when this entry was made.",
    )
    enmity_change = models.IntegerField(
        default=0,
        help_text="Change in enmity value when this entry was made.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Thread Journal Entry"
        verbose_name_plural = "Thread Journal Entries"

    def __str__(self) -> str:
        return f"Journal entry on {self.thread} by {self.author}"


class ThreadResonance(models.Model):
    """
    A resonance attached to a thread.

    Threads can carry resonances that affect both characters when
    interacting with each other. These emerge from shared experiences.
    """

    thread = models.ForeignKey(
        Thread,
        on_delete=models.CASCADE,
        related_name="resonances",
        help_text="The thread this resonance is attached to.",
    )
    resonance = models.ForeignKey(
        Resonance,
        on_delete=models.PROTECT,
        related_name="thread_attachments",
        help_text="The resonance type.",
    )
    strength = models.CharField(
        max_length=20,
        choices=ResonanceStrength.choices,
        default=ResonanceStrength.MODERATE,
        help_text="The strength of this resonance on the thread.",
    )
    flavor_text = models.TextField(
        blank=True,
        help_text="How this resonance manifests in the relationship.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["thread", "resonance"]
        verbose_name = "Thread Resonance"
        verbose_name_plural = "Thread Resonances"

    def __str__(self) -> str:
        return f"{self.resonance} on {self.thread}"
