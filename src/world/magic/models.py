"""
Magic system models.

This module contains the foundational models for the magic system:
- CharacterAura: Tracks a character's affinity percentages
- Gift: Thematic collections of magical techniques
- Technique: Player-created magical abilities
- TechniqueStyle/EffectType/Restriction: Technique building blocks
- CharacterAnima: Magical resource tracking
- CharacterAnimaRitual: Personalized recovery rituals (stat+skill+resonance)
- Motif: Character-level magical aesthetic
- Thread: Magical relationships between characters

Affinities and Resonances are now managed via ModifierType in the mechanics app.
"""

from decimal import Decimal
from functools import cached_property

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from evennia.objects.models import ObjectDB
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.magic.types import (
    AffinityType,
    ResonanceScope,
    ResonanceStrength,
)


class EffectTypeManager(NaturalKeyManager):
    """Manager for EffectType with natural key support."""


class EffectType(NaturalKeyMixin, SharedMemoryModel):
    """
    Type of magical effect.

    Defines types of magical effects (e.g., Attack, Defense, Buff, Movement).
    Some effects have power scaling (Attack, Defense), others are binary
    (Movement, Flight). Used in character creation to categorize techniques.
    """

    name = models.CharField(
        max_length=50,
        unique=True,
        help_text="Effect type name (e.g., 'Attack', 'Defense', 'Movement').",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of this effect type.",
    )
    base_power = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Base power value for scaled effects. Null for binary effects.",
    )
    base_anima_cost = models.PositiveIntegerField(
        default=2,
        help_text="Base anima cost for this effect type.",
    )
    has_power_scaling = models.BooleanField(
        default=True,
        help_text="Whether this effect type uses power scaling.",
    )

    objects = EffectTypeManager()

    class Meta:
        verbose_name = "Effect Type"
        verbose_name_plural = "Effect Types"

    class NaturalKeyConfig:
        fields = ["name"]

    def __str__(self) -> str:
        return self.name


class TechniqueStyleManager(NaturalKeyManager):
    """Manager for TechniqueStyle with natural key support."""


class TechniqueStyle(NaturalKeyMixin, SharedMemoryModel):
    """
    Style of magical technique.

    Defines how a magical technique manifests (e.g., Manifestation, Subtle,
    Imbued, Prayer, Incantation). Different Paths have access to different
    technique styles.
    """

    name = models.CharField(
        max_length=50,
        unique=True,
        help_text="Style name (e.g., 'Manifestation', 'Subtle', 'Prayer').",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of this technique style.",
    )
    allowed_paths = models.ManyToManyField(
        "classes.Path",
        blank=True,
        related_name="allowed_styles",
        help_text="Paths that can use techniques of this style.",
    )

    objects = TechniqueStyleManager()

    class Meta:
        ordering = ["name"]
        verbose_name = "Technique Style"
        verbose_name_plural = "Technique Styles"

    class NaturalKeyConfig:
        fields = ["name"]

    def __str__(self) -> str:
        return self.name

    @cached_property
    def cached_allowed_paths(self) -> list:
        """Paths that can use this style. Supports Prefetch(to_attr=)."""
        return list(self.allowed_paths.all())


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
    Resonance types are now ModifierType entries with category='resonance'.
    """

    character = models.ForeignKey(
        ObjectDB,
        on_delete=models.CASCADE,
        related_name="resonances",
        help_text="The character this resonance is attached to.",
    )
    resonance = models.ForeignKey(
        "mechanics.ModifierType",
        on_delete=models.PROTECT,
        related_name="character_resonance_attachments",
        help_text="The resonance type (must be category='resonance').",
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
        return f"{self.resonance.name} on {self.character}"

    def clean(self) -> None:
        """Validate that resonance is a resonance-category ModifierType."""
        if self.resonance_id and self.resonance.category.name != "resonance":
            msg = "Resonance must be a ModifierType with category='resonance'."
            raise ValidationError(msg)


class GiftManager(NaturalKeyManager):
    """Manager for Gift with natural key support."""


class Gift(NaturalKeyMixin, SharedMemoryModel):
    """
    A thematic collection of magical powers.

    Gifts represent a character's supernatural portfolio - like "Shadow Majesty"
    for dark regal influence. Each Gift contains multiple Powers that unlock
    as the character levels.

    Affinities and Resonances are now ModifierType entries.
    """

    name = models.CharField(
        max_length=200,
        unique=True,
        help_text="Display name for this gift.",
    )
    affinity = models.ForeignKey(
        "mechanics.ModifierType",
        on_delete=models.PROTECT,
        related_name="gifts",
        help_text="The primary affinity of this gift (must be category='affinity').",
    )
    description = models.TextField(
        blank=True,
        help_text="Player-facing description of this gift.",
    )
    resonances = models.ManyToManyField(
        "mechanics.ModifierType",
        blank=True,
        related_name="gift_resonances",
        help_text="Resonances associated with this gift (must be category='resonance').",
    )
    creator = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_gifts",
        help_text="Character who created this gift.",
    )

    objects = GiftManager()

    class NaturalKeyConfig:
        fields = ["name"]
        dependencies = ["world.mechanics.ModifierType"]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        """Validate that affinity is an affinity-category ModifierType."""
        if self.affinity_id and self.affinity.category.name != "affinity":
            msg = "Affinity must be a ModifierType with category='affinity'."
            raise ValidationError(msg)

    @cached_property
    def cached_resonances(self) -> list:
        """Resonances for this gift. Supports Prefetch(to_attr=)."""
        return list(self.resonances.all())

    @cached_property
    def cached_techniques(self) -> list:
        """Techniques for this gift. Supports Prefetch(to_attr=)."""
        return list(self.techniques.all())


class CharacterGift(models.Model):
    """
    Links a character to a Gift they know.

    Characters start with one Gift at creation and may learn more
    through play, training, or transformation.
    """

    character = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="character_gifts",
        help_text="The character who knows this gift.",
    )
    gift = models.ForeignKey(
        Gift,
        on_delete=models.PROTECT,
        related_name="character_grants",
        help_text="The gift known.",
    )
    acquired_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this gift was acquired.",
    )

    class Meta:
        unique_together = ["character", "gift"]
        verbose_name = "Character Gift"
        verbose_name_plural = "Character Gifts"

    def __str__(self) -> str:
        return f"{self.gift} on {self.character}"


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


class CharacterAnimaRitual(models.Model):
    """
    A character's personalized anima recovery ritual.

    Defines the stat + skill + optional specialization + resonance
    combination used for social recovery activities.
    """

    character = models.OneToOneField(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="anima_ritual",
        help_text="The character this ritual belongs to.",
    )
    stat = models.ForeignKey(
        "traits.Trait",
        on_delete=models.PROTECT,
        limit_choices_to={"trait_type": "stat"},
        related_name="anima_rituals",
        help_text="The primary stat used in this ritual.",
    )
    skill = models.ForeignKey(
        "skills.Skill",
        on_delete=models.PROTECT,
        related_name="anima_rituals",
        help_text="The skill used in this ritual.",
    )
    specialization = models.ForeignKey(
        "skills.Specialization",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="anima_rituals",
        help_text="Optional specialization for this ritual.",
    )
    resonance = models.ForeignKey(
        "mechanics.ModifierType",
        on_delete=models.PROTECT,
        limit_choices_to={"category__name": "resonance"},
        related_name="anima_rituals",
        help_text="The resonance that powers this ritual.",
    )
    description = models.TextField(
        help_text="Social activity that restores anima.",
    )

    class Meta:
        verbose_name = "Character Anima Ritual"
        verbose_name_plural = "Character Anima Rituals"

    def __str__(self) -> str:
        return f"Anima Ritual of {self.character}"


class AnimaRitualPerformance(models.Model):
    """
    Historical record of an anima ritual performance.

    Links to scene for RP history, tracks success and recovery.
    """

    ritual = models.ForeignKey(
        CharacterAnimaRitual,
        on_delete=models.CASCADE,
        related_name="performances",
        help_text="The ritual that was performed.",
    )
    performed_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the ritual was performed.",
    )
    target_character = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.SET_NULL,
        null=True,
        related_name="anima_ritual_participations",
        help_text="The character the ritual was performed with.",
    )
    scene = models.ForeignKey(
        "scenes.Scene",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="anima_ritual_performances",
        help_text="The scene where this ritual was performed.",
    )
    was_successful = models.BooleanField(
        help_text="Whether the ritual succeeded.",
    )
    anima_recovered = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Amount of anima recovered (if successful).",
    )
    notes = models.TextField(
        blank=True,
        help_text="Optional notes about this performance.",
    )

    class Meta:
        ordering = ["-performed_at"]
        verbose_name = "Anima Ritual Performance"
        verbose_name_plural = "Anima Ritual Performances"

    def __str__(self) -> str:
        status = "success" if self.was_successful else "failure"
        return f"{self.ritual} ({status}) at {self.performed_at}"


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
        "mechanics.ModifierType",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="thread_type_grants",
        help_text="Resonance granted by this thread type (must be category='resonance').",
    )

    objects = ThreadTypeManager()

    class Meta:
        ordering = ["name"]
        verbose_name = "Thread Type"
        verbose_name_plural = "Thread Types"

    class NaturalKeyConfig:
        fields = ["slug"]
        dependencies = ["world.mechanics.ModifierType"]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        """Validate that grants_resonance is a resonance-category ModifierType."""
        if self.grants_resonance_id and self.grants_resonance.category.name != "resonance":
            msg = "grants_resonance must be a ModifierType with category='resonance'."
            raise ValidationError(msg)


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
    Resonance types are now ModifierType entries with category='resonance'.
    """

    thread = models.ForeignKey(
        Thread,
        on_delete=models.CASCADE,
        related_name="resonances",
        help_text="The thread this resonance is attached to.",
    )
    resonance = models.ForeignKey(
        "mechanics.ModifierType",
        on_delete=models.PROTECT,
        related_name="thread_resonance_attachments",
        help_text="The resonance type (must be category='resonance').",
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
        return f"{self.resonance.name} on {self.thread}"

    def clean(self) -> None:
        """Validate that resonance is a resonance-category ModifierType."""
        if self.resonance_id and self.resonance.category.name != "resonance":
            msg = "Resonance must be a ModifierType with category='resonance'."
            raise ValidationError(msg)


class RestrictionManager(NaturalKeyManager):
    """Manager for Restriction with natural key support."""


class Restriction(NaturalKeyMixin, SharedMemoryModel):
    """
    A limitation that can be applied to techniques for power bonuses.

    Restrictions like "Touch Range" or "Undead Only" limit how a technique
    can be used in exchange for increased power. Each restriction specifies
    which effect types it can apply to.
    """

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Name of the restriction (e.g., 'Touch Range', 'Undead Only').",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of this restriction's limitations.",
    )
    power_bonus = models.PositiveIntegerField(
        default=10,
        help_text="Power bonus granted when this restriction is applied.",
    )
    allowed_effect_types = models.ManyToManyField(
        EffectType,
        blank=True,
        related_name="available_restrictions",
        help_text="Effect types this restriction can be applied to.",
    )

    objects = RestrictionManager()

    class Meta:
        verbose_name = "Restriction"
        verbose_name_plural = "Restrictions"

    class NaturalKeyConfig:
        fields = ["name"]

    def __str__(self) -> str:
        return f"{self.name} (+{self.power_bonus})"

    @cached_property
    def cached_allowed_effect_types(self) -> list:
        """Effect types this restriction can apply to. Supports Prefetch(to_attr=)."""
        return list(self.allowed_effect_types.all())


class IntensityTier(NaturalKeyMixin, SharedMemoryModel):
    """
    Configurable thresholds for power intensity effects.

    Defines named tiers (e.g., Minor, Moderate, Major) based on
    calculated power thresholds. Used to determine narrative
    descriptions and control modifiers for technique effects.
    """

    name = models.CharField(
        max_length=50,
        unique=True,
        help_text="Display name for this tier (e.g., 'Minor', 'Moderate').",
    )
    threshold = models.PositiveIntegerField(
        unique=True,
        help_text="Minimum calculated power to reach this tier.",
    )
    control_modifier = models.IntegerField(
        default=0,
        help_text="Modifier to control rolls at this intensity.",
    )
    description = models.TextField(
        blank=True,
        help_text="Player-facing description of this intensity level.",
    )
    admin_notes = models.TextField(
        blank=True,
        help_text="Staff-only notes about this tier.",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        ordering = ["threshold"]
        verbose_name = "Intensity Tier"
        verbose_name_plural = "Intensity Tiers"

    def __str__(self) -> str:
        return f"{self.name} (threshold: {self.threshold})"


class Technique(models.Model):
    """
    A specific magical ability within a Gift.

    Techniques represent player-created magical abilities. They have a level
    (with tier derived from level), style, effect type, optional restrictions,
    and calculated power. Unlike lookup tables, techniques are unique per
    character and not shared.
    """

    name = models.CharField(
        max_length=200,
        help_text="Name of the technique (not unique - different characters can have same name).",
    )
    gift = models.ForeignKey(
        Gift,
        on_delete=models.CASCADE,
        related_name="techniques",
        help_text="The gift this technique belongs to.",
    )
    style = models.ForeignKey(
        TechniqueStyle,
        on_delete=models.PROTECT,
        related_name="techniques",
        help_text="The style of this technique (restricted by Path).",
    )
    effect_type = models.ForeignKey(
        EffectType,
        on_delete=models.PROTECT,
        related_name="techniques",
        help_text="The type of effect this technique produces.",
    )
    restrictions = models.ManyToManyField(
        Restriction,
        blank=True,
        related_name="techniques",
        help_text="Restrictions applied to this technique for power bonuses.",
    )
    level = models.PositiveIntegerField(
        default=1,
        help_text="The level of this technique (determines tier).",
    )
    anima_cost = models.PositiveIntegerField(
        help_text="Anima cost to use this technique.",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of what this technique does.",
    )
    creator = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_techniques",
        help_text="Character who created this technique.",
    )

    class Meta:
        verbose_name = "Technique"
        verbose_name_plural = "Techniques"

    def __str__(self) -> str:
        return f"{self.name} ({self.gift})"

    # Tier thresholds: level ranges for each tier
    TIER_1_MAX = 5
    TIER_2_MAX = 10
    TIER_3_MAX = 15
    TIER_4_MAX = 20

    @property
    def tier(self) -> int:
        """
        Tier derived from level.

        1-5 = T1, 6-10 = T2, 11-15 = T3, 16-20 = T4, 21+ = T5
        """
        if self.level <= self.TIER_1_MAX:
            return 1
        if self.level <= self.TIER_2_MAX:
            return 2
        if self.level <= self.TIER_3_MAX:
            return 3
        if self.level <= self.TIER_4_MAX:
            return 4
        return 5

    @property
    def calculated_power(self) -> int | None:
        """
        Base power + sum of restriction bonuses.

        Returns None for effect types without power scaling (binary effects).
        """
        if not self.effect_type.has_power_scaling:
            return None
        base = self.effect_type.base_power or 0
        restriction_bonus = sum(r.power_bonus for r in self.restrictions.all())
        return base + restriction_bonus


class CharacterTechnique(models.Model):
    """
    Links a character to a Technique they know.

    Characters learn techniques under Gifts they know.
    Techniques can be taught individually.
    """

    character = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="character_techniques",
        help_text="The character who knows this technique.",
    )
    technique = models.ForeignKey(
        Technique,
        on_delete=models.PROTECT,
        related_name="character_grants",
        help_text="The technique known.",
    )
    acquired_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this technique was acquired.",
    )

    class Meta:
        unique_together = ["character", "technique"]
        verbose_name = "Character Technique"
        verbose_name_plural = "Character Techniques"

    def __str__(self) -> str:
        return f"{self.technique} on {self.character}"


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


class CharacterFacet(models.Model):
    """
    Links a character to a facet with an associated resonance.

    Players assign facets to their resonances to define what the imagery
    means to their character. Example: Spider assigned to Praedari resonance
    with flavor "Patient predator, weaving traps."
    """

    character = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="character_facets",
        help_text="The character who has this facet.",
    )
    facet = models.ForeignKey(
        Facet,
        on_delete=models.PROTECT,
        related_name="character_assignments",
        help_text="The facet imagery.",
    )
    resonance = models.ForeignKey(
        "mechanics.ModifierType",
        on_delete=models.PROTECT,
        limit_choices_to={"category__name": "resonance"},
        related_name="character_facet_assignments",
        help_text="The resonance this facet is linked to.",
    )
    flavor_text = models.TextField(
        blank=True,
        default="",
        help_text="What this facet means to the character.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["character", "facet"]
        verbose_name = "Character Facet"
        verbose_name_plural = "Character Facets"

    def __str__(self) -> str:
        return f"{self.facet.name} → {self.resonance.name} on {self.character}"


class CharacterAffinityTotal(SharedMemoryModel):
    """
    Aggregate affinity total for a character.

    Updated when affinity sources change (distinctions, conditions, etc.).
    Used to calculate aura percentages dynamically.
    """

    character = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="affinity_totals",
    )
    affinity_type = models.CharField(
        max_length=20,
        choices=AffinityType.choices,
    )
    total = models.IntegerField(default=0)

    class Meta:
        unique_together = [("character", "affinity_type")]
        verbose_name = "Character Affinity Total"
        verbose_name_plural = "Character Affinity Totals"

    def __str__(self) -> str:
        return f"{self.character}: {self.affinity_type} = {self.total}"


class CharacterResonanceTotal(SharedMemoryModel):
    """
    Aggregate resonance total for a character.

    Updated when resonance sources change. Contributes to affinity
    totals via the resonance's affiliated_affinity.
    """

    character = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="resonance_totals",
    )
    resonance = models.ForeignKey(
        "mechanics.ModifierType",
        on_delete=models.PROTECT,
        related_name="character_totals",
    )
    total = models.IntegerField(default=0)

    class Meta:
        unique_together = [("character", "resonance")]
        verbose_name = "Character Resonance Total"
        verbose_name_plural = "Character Resonance Totals"

    def __str__(self) -> str:
        return f"{self.character}: {self.resonance.name} = {self.total}"


class Motif(models.Model):
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


class MotifResonance(models.Model):
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
        "mechanics.ModifierType",
        on_delete=models.PROTECT,
        limit_choices_to={"category__name": "resonance"},
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


class MotifResonanceAssociation(models.Model):
    """
    Links a motif resonance to a facet (hierarchical imagery/symbolism).

    Maximum 5 facets per motif resonance (enforced in clean).
    """

    MAX_FACETS_PER_RESONANCE = 5

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

    def clean(self) -> None:
        """Validate maximum facets per motif resonance."""
        if self.motif_resonance_id:
            current_count = (
                MotifResonanceAssociation.objects.filter(motif_resonance=self.motif_resonance)
                .exclude(pk=self.pk)
                .count()
            )
            if current_count >= self.MAX_FACETS_PER_RESONANCE:
                msg = f"Maximum {self.MAX_FACETS_PER_RESONANCE} facets per resonance."
                raise ValidationError(msg)

    def save(self, *args, **kwargs) -> None:
        self.clean()
        super().save(*args, **kwargs)
