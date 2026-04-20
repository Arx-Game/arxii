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

Affinities and Resonances are proper domain models (Affinity, Resonance) in this app.

Note: The legacy 5-axis Thread family (Thread, ThreadType, ThreadJournal,
ThreadResonance) was removed in Phase 2 of the Resonance Pivot. A new Thread
model with a discriminator + typed FKs is reintroduced in Phase 4.
"""

from decimal import Decimal
from functools import cached_property
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from evennia.objects.models import ObjectDB
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.magic.constants import (
    THREADWEAVING_ITEM_TYPECLASSES,
    AlterationTier,
    CantripArchetype,
    EffectKind,
    PendingAlterationStatus,
    RitualExecutionKind,
    TargetKind,
    VitalBonusTarget,
)
from world.magic.types import (
    AffinityType,
)

if TYPE_CHECKING:
    from world.conditions.models import CapabilityType


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


class CharacterAura(SharedMemoryModel):
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
    glimpse_story = models.TextField(
        blank=True,
        help_text="Narrative of the character's first magical awakening (The Glimpse).",
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


class CharacterResonance(SharedMemoryModel):
    """Per-character per-resonance row.

    Identity (the row exists = "this character is associated with this
    resonance") and currency bucket (`balance` is spendable, `lifetime_earned`
    is monotonic). See Resonance Pivot Spec A §2.2.
    """

    character_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="resonances",
        help_text="The character sheet this resonance is attached to.",
    )
    resonance = models.ForeignKey(
        Resonance,
        on_delete=models.PROTECT,
        related_name="character_resonances",
        help_text="The resonance type.",
    )
    balance = models.PositiveIntegerField(
        default=0,
        help_text="Spendable resonance currency.",
    )
    lifetime_earned = models.PositiveIntegerField(
        default=0,
        help_text="Monotonic total of resonance earned (never decremented).",
    )
    claimed_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this resonance row was created (claimed by the character).",
    )
    flavor_text = models.TextField(
        blank=True,
        help_text="Optional player-defined description of how this resonance manifests.",
    )

    class Meta:
        unique_together = (("character_sheet", "resonance"),)
        verbose_name = "Character Resonance"
        verbose_name_plural = "Character Resonances"

    def __str__(self) -> str:
        return f"{self.resonance.name} on {self.character_sheet}"


class GiftManager(NaturalKeyManager):
    """Manager for Gift with natural key support."""


class Gift(NaturalKeyMixin, SharedMemoryModel):
    """
    A thematic collection of magical powers.

    Gifts represent a character's supernatural portfolio - like "Shadow Majesty"
    for dark regal influence. Each Gift contains multiple Powers that unlock
    as the character levels.

    Affinities and Resonances are proper domain models.
    """

    name = models.CharField(
        max_length=200,
        unique=True,
        help_text="Display name for this gift.",
    )
    description = models.TextField(
        blank=True,
        help_text="Player-facing description of this gift.",
    )
    resonances = models.ManyToManyField(
        Resonance,
        blank=True,
        related_name="gifts",
        help_text="Resonances associated with this gift.",
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

    def __str__(self) -> str:
        return self.name

    def get_affinity_breakdown(self) -> dict[str, int]:
        """Derive affinity from resonances' affinities."""
        counts: dict[str, int] = {}
        for resonance in self.resonances.select_related("affinity").all():
            aff_name = resonance.affinity.name
            counts[aff_name] = counts.get(aff_name, 0) + 1
        return counts

    @cached_property
    def cached_resonances(self) -> list:
        """Resonances for this gift. Supports Prefetch(to_attr=)."""
        return list(self.resonances.all())

    @cached_property
    def cached_techniques(self) -> list:
        """Techniques for this gift. Supports Prefetch(to_attr=)."""
        return list(self.techniques.all())


class CharacterGift(SharedMemoryModel):
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


class TraditionManager(NaturalKeyManager):
    """Manager for Tradition with natural key support."""


class Tradition(NaturalKeyMixin, SharedMemoryModel):
    """
    A magical tradition representing a school of practice or philosophy.

    Traditions group practitioners who share techniques, beliefs, or methods.
    A tradition may be associated with a society but can also exist independently.
    """

    name = models.CharField(
        max_length=200,
        unique=True,
        help_text="Display name for this tradition.",
    )
    description = models.TextField(
        blank=True,
        help_text="Player-facing description of this tradition's philosophy and practices.",
    )
    society = models.ForeignKey(
        "societies.Society",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="traditions",
        help_text="The society this tradition is associated with, if any.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this tradition is currently available for selection.",
    )
    sort_order = models.PositiveIntegerField(
        default=0,
        help_text="Display ordering within lists (lower numbers appear first).",
    )

    objects = TraditionManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Tradition"
        verbose_name_plural = "Traditions"

    def __str__(self) -> str:
        return self.name


class CharacterTradition(SharedMemoryModel):
    """
    Links a character to a tradition they belong to.

    Characters may join traditions during creation or through play.
    A character cannot belong to the same tradition twice.
    """

    character = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="character_traditions",
        help_text="The character who belongs to this tradition.",
    )
    tradition = models.ForeignKey(
        Tradition,
        on_delete=models.PROTECT,
        related_name="character_traditions",
        help_text="The tradition the character belongs to.",
    )
    acquired_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the character joined this tradition.",
    )

    class Meta:
        unique_together = ["character", "tradition"]
        verbose_name = "Character Tradition"
        verbose_name_plural = "Character Traditions"

    def __str__(self) -> str:
        return f"{self.tradition} on {self.character}"


class CharacterAnima(SharedMemoryModel):
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
    pre_audere_maximum = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Stored maximum before Audere expanded the pool. Null when not in Audere.",
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


class CharacterAnimaRitual(SharedMemoryModel):
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
        Resonance,
        on_delete=models.PROTECT,
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


class AnimaRitualPerformance(SharedMemoryModel):
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


class Technique(SharedMemoryModel):
    """
    A specific magical ability within a Gift.

    Techniques represent magical abilities with intensity (raw power) and control
    (safety/precision). When intensity exceeds control at runtime, effects become
    unpredictable and anima cost can spike. Level gates progression and derives tier.
    Unlike lookup tables, techniques are unique per character and not shared.
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
    intensity = models.PositiveIntegerField(
        default=1,
        help_text="Base power of the technique. Determines damage and effect strength.",
    )
    control = models.PositiveIntegerField(
        default=1,
        help_text=(
            "Base safety/precision. When intensity exceeds control at runtime, "
            "effects become unpredictable and anima cost can spike."
        ),
    )
    anima_cost = models.PositiveIntegerField(
        help_text="Anima cost to use this technique.",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of what this technique does.",
    )
    source_cantrip = models.ForeignKey(
        "magic.Cantrip",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_techniques",
        help_text="The cantrip template this technique was created from, if any.",
    )
    creator = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="authored_techniques",
        help_text="Character who created this technique.",
    )
    action_template = models.ForeignKey(
        "actions.ActionTemplate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="techniques",
        help_text="Resolution spec for using this technique outside challenge contexts.",
    )

    class Meta:
        verbose_name = "Technique"
        verbose_name_plural = "Techniques"

    @cached_property
    def cached_restrictions(self) -> list:
        """Restrictions for this technique. Supports Prefetch(to_attr=)."""
        return list(self.restrictions.all())

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


class TechniqueCapabilityGrant(SharedMemoryModel):
    """
    A Capability granted by a Technique, with value derived from intensity.

    effective_value = base_value + (intensity_multiplier * technique.intensity)

    A single Technique typically grants 2-4 Capabilities.
    """

    technique = models.ForeignKey(
        Technique,
        on_delete=models.CASCADE,
        related_name="capability_grants",
    )
    capability = models.ForeignKey(
        "conditions.CapabilityType",
        on_delete=models.CASCADE,
        related_name="technique_grants",
    )
    base_value = models.IntegerField(
        default=0,
        help_text="Flat Capability contribution.",
    )
    intensity_multiplier = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Multiplied by the Technique's current intensity.",
    )
    prerequisite = models.ForeignKey(
        "mechanics.Prerequisite",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="technique_grants",
        help_text="Source-specific prerequisite, checked in addition to Capability-level ones.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["technique", "capability"],
                name="technique_capability_grant_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.technique.name} grants {self.capability.name}"

    def calculate_value(self, intensity: int | None = None) -> int:
        """Calculate effective Capability value."""
        effective_intensity = intensity if intensity is not None else self.technique.intensity
        return int(self.base_value + (self.intensity_multiplier * Decimal(effective_intensity)))


class CharacterTechnique(SharedMemoryModel):
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


class CharacterFacet(SharedMemoryModel):
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
        Resonance,
        on_delete=models.PROTECT,
        related_name="character_facets",
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
    affinity = models.ForeignKey(
        Affinity,
        on_delete=models.PROTECT,
        related_name="character_totals",
    )
    total = models.IntegerField(default=0)

    class Meta:
        unique_together = [("character", "affinity")]
        verbose_name = "Character Affinity Total"
        verbose_name_plural = "Character Affinity Totals"

    def __str__(self) -> str:
        return f"{self.character}: {self.affinity.name} = {self.total}"


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


class MotifResonanceAssociation(SharedMemoryModel):
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


class Reincarnation(SharedMemoryModel):
    """
    Links a character to a past life via their Atavism gift.

    Created at character finalization when a character has the Old Soul
    distinction. Staff/GMs fill in past_life details later as a story arc.
    Future: past_life fields may be replaced by a FK to a PastLife model
    when multiple characters can share the same historical figure.
    """

    character = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="reincarnations",
        help_text="The character who is a reincarnation.",
    )
    gift = models.OneToOneField(
        Gift,
        on_delete=models.CASCADE,
        related_name="reincarnation",
        help_text="The Atavism gift manifesting the past life.",
    )
    past_life_name = models.CharField(
        max_length=200,
        blank=True,
        help_text="Name of the past life (filled in by staff/GM).",
    )
    past_life_notes = models.TextField(
        blank=True,
        help_text="Notes about the past life (filled in by staff/GM).",
    )

    class Meta:
        verbose_name = "Reincarnation"
        verbose_name_plural = "Reincarnations"

    def __str__(self) -> str:
        name = self.past_life_name or "Unknown past life"
        return f"Reincarnation of {name} ({self.character})"


class Cantrip(SharedMemoryModel):
    """Staff-curated starter technique template for character creation.

    A cantrip is a baby technique — same mechanical system, just preset at low values.
    At CG finalization, the cantrip creates a real Technique in the character's Gift.
    Mechanical fields (intensity, control, anima cost) are hidden from the player;
    they only see name, description, archetype grouping, and optional facet selection.
    """

    name = models.CharField(max_length=200, unique=True)
    description = models.TextField()
    archetype = models.CharField(
        max_length=20,
        choices=CantripArchetype.choices,
        help_text="Player-facing category for CG grouping: attack, defense, buff, debuff, utility.",
    )
    effect_type = models.ForeignKey(
        EffectType,
        on_delete=models.PROTECT,
        related_name="cantrips",
        help_text="Mechanical effect type (Attack, Defense, Buff, etc.).",
    )
    style = models.ForeignKey(
        TechniqueStyle,
        on_delete=models.PROTECT,
        related_name="cantrips",
        help_text="How this cantrip manifests. Filtered by character's Path at CG.",
    )
    base_intensity = models.PositiveIntegerField(
        default=1,
        help_text="Starting intensity for the technique created from this cantrip.",
    )
    base_control = models.PositiveIntegerField(
        default=1,
        help_text="Starting control for the technique created from this cantrip.",
    )
    base_anima_cost = models.PositiveIntegerField(
        default=5,
        help_text="Starting anima cost for the technique created from this cantrip.",
    )
    requires_facet = models.BooleanField(
        default=False,
        help_text=("If true, player must pick a facet (element/damage type) from allowed_facets."),
    )
    facet_prompt = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text=(
            'Player-facing dropdown label, e.g. "Choose your element". '
            "Only used when requires_facet=True."
        ),
    )
    allowed_facets = models.ManyToManyField(
        "magic.Facet",
        blank=True,
        related_name="cantrips",
        help_text="Curated list of valid facets for this cantrip's dropdown.",
    )
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Cantrip"
        verbose_name_plural = "Cantrips"

    @cached_property
    def cached_allowed_facets(self) -> list:
        """Allowed facets for this cantrip. Supports Prefetch(to_attr=)."""
        return list(self.allowed_facets.all())

    def __str__(self) -> str:
        return self.name


class SoulfrayConfig(SharedMemoryModel):
    """Global configuration for Soulfray severity accumulation and resilience checks.

    Single-row table (queried with .first()), same pattern as AudereThreshold.
    """

    soulfray_threshold_ratio = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        help_text=(
            "Anima ratio (current/max) below which technique use "
            "accumulates Soulfray severity. E.g., 0.30 = below 30%%."
        ),
    )
    severity_scale = models.PositiveIntegerField(
        help_text="Base scaling factor for converting depletion into severity.",
    )
    deficit_scale = models.PositiveIntegerField(
        help_text="Additional scaling factor for deficit (anima spent beyond zero).",
    )
    resilience_check_type = models.ForeignKey(
        "checks.CheckType",
        on_delete=models.PROTECT,
        help_text="Check type for Soulfray resilience (e.g., magical endurance).",
    )
    base_check_difficulty = models.PositiveIntegerField(
        help_text="Base difficulty for the resilience check before stage modifiers.",
    )

    class Meta:
        verbose_name = "Soulfray Configuration"
        verbose_name_plural = "Soulfray Configurations"

    def __str__(self) -> str:
        return (
            f"SoulfrayConfig(threshold={self.soulfray_threshold_ratio}, "
            f"scale={self.severity_scale})"
        )


class MishapPoolTier(SharedMemoryModel):
    """Maps control deficit ranges to consequence pools for imprecision mishaps.

    Ranges must not overlap. Validated via clean().
    Control mishap pools must never contain character_loss consequences.
    """

    min_deficit = models.PositiveIntegerField(
        help_text="Minimum control deficit for this tier (inclusive).",
    )
    max_deficit = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Maximum control deficit for this tier (inclusive). Null = no upper bound.",
    )
    consequence_pool = models.ForeignKey(
        "actions.ConsequencePool",
        on_delete=models.CASCADE,
        related_name="mishap_tiers",
        help_text="Consequence pool for this deficit range.",
    )

    def __str__(self) -> str:
        upper = self.max_deficit or "\u221e"
        return f"Mishap {self.min_deficit}-{upper}"

    def clean(self) -> None:
        """Validate that this tier's range does not overlap with existing tiers."""
        overlapping = MishapPoolTier.objects.exclude(pk=self.pk)
        if self.max_deficit is not None:
            overlapping = overlapping.filter(
                min_deficit__lte=self.max_deficit,
            ).exclude(
                max_deficit__isnull=False,
                max_deficit__lt=self.min_deficit,
            )
        else:
            overlapping = overlapping.exclude(
                max_deficit__isnull=False,
                max_deficit__lt=self.min_deficit,
            )
        if overlapping.exists():
            msg = "Deficit range overlaps with an existing MishapPoolTier."
            raise ValidationError(msg)


class TechniqueOutcomeModifier(SharedMemoryModel):
    """Maps technique check outcome tiers to signed modifiers for the Soulfray resilience check.

    When a character uses a technique while in Soulfray, the technique's check outcome
    modifies the subsequent resilience check. Botching penalizes; critting helps.
    """

    outcome = models.OneToOneField(
        "traits.CheckOutcome",
        on_delete=models.CASCADE,
        related_name="technique_warp_modifier",
        help_text="The technique check outcome tier.",
    )
    modifier_value = models.IntegerField(
        help_text="Signed modifier applied to the Soulfray resilience check. Negative = penalty.",
    )

    class Meta:
        verbose_name = "Technique Outcome Modifier"
        verbose_name_plural = "Technique Outcome Modifiers"

    def __str__(self) -> str:
        sign = "+" if self.modifier_value >= 0 else ""
        return f"{self.outcome}: {sign}{self.modifier_value} to resilience"


# =============================================================================
# Magical Alterations
# =============================================================================


class MagicalAlterationTemplate(SharedMemoryModel):
    """Magic-specific metadata layered on top of a ConditionTemplate.

    A magical alteration IS a condition — runtime effects (check modifiers,
    capability effects, resistance, properties, descriptions) live on the
    OneToOne'd ConditionTemplate. This table adds authoring slots, tier
    classification, and origin context.
    """

    condition_template = models.OneToOneField(
        "conditions.ConditionTemplate",
        on_delete=models.CASCADE,
        related_name="magical_alteration",
    )
    tier = models.PositiveSmallIntegerField(
        choices=AlterationTier.choices,
        help_text="Severity tier 1 (cosmetic) through 5 (body partially remade).",
    )
    origin_affinity = models.ForeignKey(
        Affinity,
        on_delete=models.PROTECT,
        related_name="alteration_templates",
        help_text="Which affinity (Celestial/Primal/Abyssal) caused this.",
    )
    origin_resonance = models.ForeignKey(
        Resonance,
        on_delete=models.PROTECT,
        related_name="alteration_templates",
        help_text="The resonance channeled at overburn.",
    )
    weakness_damage_type = models.ForeignKey(
        "conditions.DamageType",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="alteration_weaknesses",
        help_text="Damage type the character is now vulnerable to.",
    )
    weakness_magnitude = models.PositiveSmallIntegerField(
        default=0,
        help_text="Vulnerability magnitude, tier-bounded.",
    )
    resonance_bonus_magnitude = models.PositiveSmallIntegerField(
        default=0,
        help_text="Bonus when channeling origin_resonance, tier-bounded.",
    )
    social_reactivity_magnitude = models.PositiveSmallIntegerField(
        default=0,
        help_text=(
            "Reaction strength from magic-phobic observers. Calibrated as "
            "situational world-friction, not character-concept blocker."
        ),
    )
    is_visible_at_rest = models.BooleanField(
        default=False,
        help_text="Shows through normal clothing? Required True at tier 4+.",
    )
    authored_by = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="authored_alterations",
        help_text="Account that authored this. NULL = system/staff seed.",
    )
    parent_template = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="variants",
        help_text="If spun off from a library entry or prior alteration.",
    )
    is_library_entry = models.BooleanField(
        default=False,
        help_text=(
            "If True, shown to players browsing tier-matched alterations. "
            "Only staff can set this flag."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.condition_template.name} (Tier {self.tier})"


class PendingAlteration(SharedMemoryModel):
    """A magical alteration owed to a character, awaiting resolution.

    Created by the MAGICAL_SCARS effect handler. Blocks progression
    spending until resolved via library browse or author-from-scratch.
    """

    character = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="pending_alterations",
    )
    status = models.CharField(
        max_length=20,
        choices=PendingAlterationStatus.choices,
        default=PendingAlterationStatus.OPEN,
    )
    tier = models.PositiveSmallIntegerField(
        choices=AlterationTier.choices,
        help_text=(
            "Required tier for resolved alteration. Upgradeable via same-scene escalation only."
        ),
    )
    triggering_scene = models.ForeignKey(
        "scenes.Scene",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="triggered_alterations",
    )
    triggering_technique = models.ForeignKey(
        Technique,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    triggering_intensity = models.IntegerField(null=True, blank=True)
    triggering_control = models.IntegerField(null=True, blank=True)
    triggering_anima_cost = models.IntegerField(null=True, blank=True)
    triggering_anima_deficit = models.IntegerField(null=True, blank=True)
    triggering_soulfray_stage = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
    )
    audere_active = models.BooleanField(default=False)
    origin_affinity = models.ForeignKey(
        Affinity,
        on_delete=models.PROTECT,
        related_name="pending_alteration_origins",
    )
    origin_resonance = models.ForeignKey(
        Resonance,
        on_delete=models.PROTECT,
        related_name="pending_alteration_origins",
    )
    resolved_alteration = models.ForeignKey(
        MagicalAlterationTemplate,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="resolved_pending",
        help_text="Set when player picks/authors a template.",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_pending_alterations",
    )
    notes = models.TextField(
        blank=True,
        help_text="Staff notes (e.g. reason for staff clear).",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["character", "status"], name="magic_pendi_charact_4fea0a_idx"),
        ]

    def __str__(self) -> str:
        return f"Pending Tier {self.tier} alteration for {self.character} ({self.status})"


class MagicalAlterationEvent(SharedMemoryModel):
    """Audit record: this character received this alteration at this moment.

    Created when a PendingAlteration resolves. Survives independently of
    the PendingAlteration and the ConditionInstance.
    """

    character = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="alteration_events",
    )
    alteration_template = models.ForeignKey(
        MagicalAlterationTemplate,
        on_delete=models.PROTECT,
        related_name="application_events",
    )
    active_condition = models.ForeignKey(
        "conditions.ConditionInstance",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alteration_events",
    )
    triggering_scene = models.ForeignKey(
        "scenes.Scene",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    triggering_technique = models.ForeignKey(
        Technique,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    triggering_intensity = models.IntegerField(null=True, blank=True)
    triggering_control = models.IntegerField(null=True, blank=True)
    triggering_anima_cost = models.IntegerField(null=True, blank=True)
    triggering_anima_deficit = models.IntegerField(null=True, blank=True)
    triggering_soulfray_stage = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
    )
    audere_active = models.BooleanField(default=False)
    applied_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(
        blank=True,
        help_text="Freeform staff/system notes.",
    )

    def __str__(self) -> str:
        return (
            f"{self.alteration_template.condition_template.name} "
            f"applied to {self.character} at {self.applied_at}"
        )


# =============================================================================
# Resonance Pivot Spec A — Phase 3 Lookup Tables
# =============================================================================


class ThreadPullCost(SharedMemoryModel):
    """Per-tier pull cost. Three rows at launch (tier 1/2/3).

    Pull-cost tuning surface — see Spec A §2.1 / §5.4 step 2. Per-tier
    numbers (resonance_cost, anima_per_thread) live here as data; the
    cost-formula shape lives in spend_resonance_for_pull. Edit values
    here for per-tier tweaks; edit the service for shape changes.
    """

    tier = models.PositiveSmallIntegerField(unique=True)
    resonance_cost = models.PositiveSmallIntegerField()
    anima_per_thread = models.PositiveSmallIntegerField()
    label = models.CharField(max_length=32)

    class Meta:
        ordering = ("tier",)

    def __str__(self) -> str:
        return f"Tier {self.tier} ({self.label})"


class ThreadXPLockedLevel(SharedMemoryModel):
    """XP-locked boundary on the internal level scale. Mirrors skills XP locks."""

    level = models.PositiveSmallIntegerField(unique=True)
    xp_cost = models.PositiveIntegerField()

    class Meta:
        ordering = ("level",)

    def __str__(self) -> str:
        return f"Lvl {self.level} (XP {self.xp_cost})"


class ThreadPullEffect(SharedMemoryModel):
    """Authored pull-effect template.

    Tier 0 is passive (always-on while anchor is in scope); tiers 1-3 are
    paid pulls. Lookup row keyed (target_kind, resonance, tier, min_thread_level).
    Payload columns are mutually exclusive per effect_kind; clean() enforces
    the legal combinations and DB CheckConstraints mirror the validation.
    """

    target_kind = models.CharField(max_length=32, choices=TargetKind.choices)
    resonance = models.ForeignKey(
        "magic.Resonance",
        on_delete=models.PROTECT,
        related_name="pull_effects",
    )
    tier = models.PositiveSmallIntegerField()  # 0..3
    min_thread_level = models.PositiveSmallIntegerField(default=0)
    effect_kind = models.CharField(max_length=32, choices=EffectKind.choices)

    flat_bonus_amount = models.SmallIntegerField(null=True, blank=True)
    intensity_bump_amount = models.SmallIntegerField(null=True, blank=True)
    vital_bonus_amount = models.SmallIntegerField(null=True, blank=True)
    vital_target = models.CharField(
        max_length=32,
        choices=VitalBonusTarget.choices,
        null=True,
        blank=True,
    )
    capability_grant = models.ForeignKey(
        "conditions.CapabilityType",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="thread_pull_effects",
    )
    narrative_snippet = models.TextField(blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["target_kind", "resonance", "tier"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["target_kind", "resonance", "tier", "min_thread_level"],
                name="threadpulleffect_lookup_key",
            ),
            # FLAT_BONUS: requires flat_bonus_amount, forbids other payloads.
            models.CheckConstraint(
                check=(
                    ~models.Q(effect_kind="FLAT_BONUS")
                    | (
                        models.Q(flat_bonus_amount__isnull=False)
                        & models.Q(intensity_bump_amount__isnull=True)
                        & models.Q(vital_bonus_amount__isnull=True)
                        & models.Q(vital_target__isnull=True)
                        & models.Q(capability_grant__isnull=True)
                    )
                ),
                name="threadpulleffect_flat_bonus_payload",
            ),
            # INTENSITY_BUMP: requires intensity_bump_amount, forbids others.
            models.CheckConstraint(
                check=(
                    ~models.Q(effect_kind="INTENSITY_BUMP")
                    | (
                        models.Q(intensity_bump_amount__isnull=False)
                        & models.Q(flat_bonus_amount__isnull=True)
                        & models.Q(vital_bonus_amount__isnull=True)
                        & models.Q(vital_target__isnull=True)
                        & models.Q(capability_grant__isnull=True)
                    )
                ),
                name="threadpulleffect_intensity_bump_payload",
            ),
            # VITAL_BONUS: requires vital_bonus_amount + vital_target, forbids others.
            models.CheckConstraint(
                check=(
                    ~models.Q(effect_kind="VITAL_BONUS")
                    | (
                        models.Q(vital_bonus_amount__isnull=False)
                        & models.Q(vital_target__isnull=False)
                        & models.Q(flat_bonus_amount__isnull=True)
                        & models.Q(intensity_bump_amount__isnull=True)
                        & models.Q(capability_grant__isnull=True)
                    )
                ),
                name="threadpulleffect_vital_bonus_payload",
            ),
            # CAPABILITY_GRANT: requires capability_grant FK, forbids numeric payloads.
            models.CheckConstraint(
                check=(
                    ~models.Q(effect_kind="CAPABILITY_GRANT")
                    | (
                        models.Q(capability_grant__isnull=False)
                        & models.Q(flat_bonus_amount__isnull=True)
                        & models.Q(intensity_bump_amount__isnull=True)
                        & models.Q(vital_bonus_amount__isnull=True)
                        & models.Q(vital_target__isnull=True)
                    )
                ),
                name="threadpulleffect_capability_grant_payload",
            ),
            # NARRATIVE_ONLY: requires non-empty snippet, forbids all other payloads.
            models.CheckConstraint(
                check=(
                    ~models.Q(effect_kind="NARRATIVE_ONLY")
                    | (
                        ~models.Q(narrative_snippet="")
                        & models.Q(flat_bonus_amount__isnull=True)
                        & models.Q(intensity_bump_amount__isnull=True)
                        & models.Q(vital_bonus_amount__isnull=True)
                        & models.Q(vital_target__isnull=True)
                        & models.Q(capability_grant__isnull=True)
                    )
                ),
                name="threadpulleffect_narrative_only_payload",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"PullEffect(t={self.target_kind} res={self.resonance_id} "
            f"tier={self.tier} kind={self.effect_kind})"
        )

    def clean(self) -> None:
        super().clean()
        numeric_fields: dict[str, int | None] = {
            "flat_bonus_amount": self.flat_bonus_amount,
            "intensity_bump_amount": self.intensity_bump_amount,
            "vital_bonus_amount": self.vital_bonus_amount,
        }
        validators = {
            EffectKind.FLAT_BONUS: self._clean_flat_bonus,
            EffectKind.INTENSITY_BUMP: self._clean_intensity_bump,
            EffectKind.VITAL_BONUS: self._clean_vital_bonus,
            EffectKind.CAPABILITY_GRANT: self._clean_capability_grant,
            EffectKind.NARRATIVE_ONLY: self._clean_narrative_only,
        }
        validator = validators.get(self.effect_kind)
        if validator is not None:
            validator(numeric_fields)

    def _clean_flat_bonus(self, numeric_fields: dict[str, int | None]) -> None:
        self._require_only("flat_bonus_amount", numeric_fields, self.capability_grant)

    def _clean_intensity_bump(self, numeric_fields: dict[str, int | None]) -> None:
        self._require_only("intensity_bump_amount", numeric_fields, self.capability_grant)

    def _clean_vital_bonus(self, numeric_fields: dict[str, int | None]) -> None:
        self._require_only("vital_bonus_amount", numeric_fields, self.capability_grant)
        if not self.vital_target:
            raise ValidationError({"vital_target": "VITAL_BONUS requires vital_target."})

    def _clean_capability_grant(self, numeric_fields: dict[str, int | None]) -> None:
        if self.capability_grant is None:
            raise ValidationError(
                {"capability_grant": "CAPABILITY_GRANT requires capability_grant."}
            )
        for name, val in numeric_fields.items():
            if val is not None:
                raise ValidationError({name: "Must be null for CAPABILITY_GRANT."})

    def _clean_narrative_only(self, numeric_fields: dict[str, int | None]) -> None:
        if not self.narrative_snippet.strip():
            raise ValidationError({"narrative_snippet": "NARRATIVE_ONLY requires snippet."})
        if self.capability_grant is not None:
            raise ValidationError({"capability_grant": "Must be null for NARRATIVE_ONLY."})
        for name, val in numeric_fields.items():
            if val is not None:
                raise ValidationError({name: "Must be null for NARRATIVE_ONLY."})

    @staticmethod
    def _require_only(
        name: str,
        numeric_fields: dict[str, int | None],
        capability: "CapabilityType | None",
    ) -> None:
        if numeric_fields[name] is None:
            raise ValidationError({name: f"{name} required for this effect_kind."})
        for other, val in numeric_fields.items():
            if other != name and val is not None:
                raise ValidationError({other: "Must be null for this effect_kind."})
        if capability is not None:
            raise ValidationError({"capability_grant": "Must be null for this effect_kind."})


class ImbuingProseTemplate(SharedMemoryModel):
    """Authored fallback prose for imbuing flow templates.

    Lookup keyed (resonance, target_kind). Either field nullable; the row
    where both are NULL is the universal fallback used when no more-specific
    template matches. Spec A §4.3.
    """

    resonance = models.ForeignKey(
        "magic.Resonance",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="imbuing_prose",
    )
    target_kind = models.CharField(
        max_length=32,
        choices=TargetKind.choices,
        null=True,
        blank=True,
    )
    prose = models.TextField()

    class Meta:
        unique_together = (("resonance", "target_kind"),)

    def __str__(self) -> str:
        res = self.resonance.name if self.resonance else "*"
        tk = self.target_kind or "*"
        return f"ImbuingProse({res} / {tk})"


class Ritual(SharedMemoryModel):
    """A ritual: authored magical procedure executed via service or flow.

    Spec A §4.3. Each Ritual is dispatched either via a registered service
    function (execution_kind=SERVICE) or via a flow definition
    (execution_kind=FLOW); never both. clean() enforces the legal shape.
    """

    name = models.CharField(max_length=120, unique=True)
    description = models.TextField()
    hedge_accessible = models.BooleanField(default=False)
    glimpse_eligible = models.BooleanField(default=False)
    narrative_prose = models.TextField()

    execution_kind = models.CharField(
        max_length=16,
        choices=RitualExecutionKind.choices,
    )
    service_function_path = models.CharField(max_length=255, blank=True)
    flow = models.ForeignKey(
        "flows.FlowDefinition",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="rituals",
    )

    site_property = models.ForeignKey(
        "mechanics.Property",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ritual_sites",
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=(
                    (
                        models.Q(execution_kind="SERVICE")
                        & ~models.Q(service_function_path="")
                        & models.Q(flow__isnull=True)
                    )
                    | (
                        models.Q(execution_kind="FLOW")
                        & models.Q(service_function_path="")
                        & models.Q(flow__isnull=False)
                    )
                ),
                name="ritual_execution_payload",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        super().clean()
        if self.execution_kind == RitualExecutionKind.SERVICE:
            if not self.service_function_path:
                raise ValidationError({"service_function_path": "SERVICE rituals require a path."})
            if self.flow is not None:
                raise ValidationError({"flow": "SERVICE rituals must not set flow."})
        elif self.execution_kind == RitualExecutionKind.FLOW:
            if self.flow is None:
                raise ValidationError({"flow": "FLOW rituals require a FlowDefinition."})
            if self.service_function_path:
                raise ValidationError(
                    {"service_function_path": ("FLOW rituals must not set service_function_path.")}
                )


class RitualComponentRequirement(SharedMemoryModel):
    """A component an actor must consume / supply to perform a Ritual.

    Spec A §4.3. Quantity is the count of items required; min_quality_tier
    optionally constrains the minimum acceptable QualityTier.
    """

    ritual = models.ForeignKey(
        "magic.Ritual",
        on_delete=models.CASCADE,
        related_name="requirements",
    )
    item_template = models.ForeignKey(
        "items.ItemTemplate",
        on_delete=models.PROTECT,
        related_name="ritual_requirements",
    )
    quantity = models.PositiveSmallIntegerField(default=1)
    min_quality_tier = models.ForeignKey(
        "items.QualityTier",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    authored_provenance = models.TextField(blank=True)

    def __str__(self) -> str:
        return f"{self.ritual.name} needs {self.quantity}x {self.item_template_id}"


# =============================================================================
# Resonance Pivot Spec A — Phase 4 Thread Model
# =============================================================================


class Thread(SharedMemoryModel):
    """Per-character thread anchored to a trait/technique/item/room/relationship.

    Discriminator + typed-FK pattern (Spec A §2.1 lines 83-151). Exactly one
    target_* column is populated, matching ``target_kind``. Three layers of
    enforcement:

    - ``clean()`` raises ValidationError on missing / mismatched targets and on
      ITEM-kind targets whose typeclass isn't in THREADWEAVING_ITEM_TYPECLASSES.
    - Per-kind CheckConstraints mirror the "exactly one target_* set, matching
      target_kind" rule at the DB layer (so misuse via .objects.create() also
      fails).
    - Per-kind partial UniqueConstraints prevent duplicate threads within the
      same (owner, resonance, target_kind, target_*) combination, while still
      allowing — for example — an ITEM thread and a ROOM thread on the same
      ObjectDB.
    """

    owner = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.PROTECT,
        related_name="threads",
        help_text="Character who owns this thread.",
    )
    resonance = models.ForeignKey(
        "magic.Resonance",
        on_delete=models.PROTECT,
        related_name="threads",
        help_text="Resonance this thread channels.",
    )
    target_kind = models.CharField(
        max_length=32,
        choices=TargetKind.choices,
        help_text="Discriminator selecting which target_* FK is populated.",
    )

    name = models.CharField(max_length=120, blank=True)
    description = models.TextField(blank=True)

    developed_points = models.PositiveIntegerField(
        default=0,
        help_text="Permanent points; advances level via ThreadLevelUnlock entries.",
    )
    level = models.PositiveSmallIntegerField(
        default=0,
        help_text="Current level on the internal scale (multiples of 10).",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    target_trait = models.ForeignKey(
        "traits.Trait",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="anchored_threads",
        help_text="Set when target_kind=TRAIT; null otherwise.",
    )
    target_technique = models.ForeignKey(
        "magic.Technique",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="anchored_threads",
        help_text="Set when target_kind=TECHNIQUE; null otherwise.",
    )
    target_object = models.ForeignKey(
        ObjectDB,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="anchored_threads",
        help_text="Set when target_kind in (ITEM, ROOM); null otherwise.",
    )
    target_relationship_track = models.ForeignKey(
        "relationships.RelationshipTrackProgress",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="anchored_threads",
        help_text="Set when target_kind=RELATIONSHIP_TRACK; null otherwise.",
    )
    target_capstone = models.ForeignKey(
        "relationships.RelationshipCapstone",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="anchored_threads",
        help_text="Set when target_kind=RELATIONSHIP_CAPSTONE; null otherwise.",
    )

    class Meta:
        constraints = [
            # ---- Per-kind partial UniqueConstraints (one per TargetKind) ---------
            models.UniqueConstraint(
                fields=["owner", "resonance", "target_trait"],
                condition=models.Q(target_kind=TargetKind.TRAIT),
                name="uniq_thread_trait",
            ),
            models.UniqueConstraint(
                fields=["owner", "resonance", "target_technique"],
                condition=models.Q(target_kind=TargetKind.TECHNIQUE),
                name="uniq_thread_technique",
            ),
            models.UniqueConstraint(
                fields=["owner", "resonance", "target_object"],
                condition=models.Q(target_kind=TargetKind.ITEM),
                name="uniq_thread_item",
            ),
            models.UniqueConstraint(
                fields=["owner", "resonance", "target_object"],
                condition=models.Q(target_kind=TargetKind.ROOM),
                name="uniq_thread_room",
            ),
            models.UniqueConstraint(
                fields=["owner", "resonance", "target_relationship_track"],
                condition=models.Q(target_kind=TargetKind.RELATIONSHIP_TRACK),
                name="uniq_thread_rel_track",
            ),
            models.UniqueConstraint(
                fields=["owner", "resonance", "target_capstone"],
                condition=models.Q(target_kind=TargetKind.RELATIONSHIP_CAPSTONE),
                name="uniq_thread_rel_capstone",
            ),
            # ---- Per-kind CheckConstraints (exactly one target_* set) -----------
            models.CheckConstraint(
                name="thread_trait_payload",
                check=(
                    ~models.Q(target_kind=TargetKind.TRAIT)
                    | (
                        models.Q(target_trait__isnull=False)
                        & models.Q(target_technique__isnull=True)
                        & models.Q(target_object__isnull=True)
                        & models.Q(target_relationship_track__isnull=True)
                        & models.Q(target_capstone__isnull=True)
                    )
                ),
            ),
            models.CheckConstraint(
                name="thread_technique_payload",
                check=(
                    ~models.Q(target_kind=TargetKind.TECHNIQUE)
                    | (
                        models.Q(target_trait__isnull=True)
                        & models.Q(target_technique__isnull=False)
                        & models.Q(target_object__isnull=True)
                        & models.Q(target_relationship_track__isnull=True)
                        & models.Q(target_capstone__isnull=True)
                    )
                ),
            ),
            models.CheckConstraint(
                name="thread_item_payload",
                check=(
                    ~models.Q(target_kind=TargetKind.ITEM)
                    | (
                        models.Q(target_trait__isnull=True)
                        & models.Q(target_technique__isnull=True)
                        & models.Q(target_object__isnull=False)
                        & models.Q(target_relationship_track__isnull=True)
                        & models.Q(target_capstone__isnull=True)
                    )
                ),
            ),
            models.CheckConstraint(
                name="thread_room_payload",
                check=(
                    ~models.Q(target_kind=TargetKind.ROOM)
                    | (
                        models.Q(target_trait__isnull=True)
                        & models.Q(target_technique__isnull=True)
                        & models.Q(target_object__isnull=False)
                        & models.Q(target_relationship_track__isnull=True)
                        & models.Q(target_capstone__isnull=True)
                    )
                ),
            ),
            models.CheckConstraint(
                name="thread_rel_track_payload",
                check=(
                    ~models.Q(target_kind=TargetKind.RELATIONSHIP_TRACK)
                    | (
                        models.Q(target_trait__isnull=True)
                        & models.Q(target_technique__isnull=True)
                        & models.Q(target_object__isnull=True)
                        & models.Q(target_relationship_track__isnull=False)
                        & models.Q(target_capstone__isnull=True)
                    )
                ),
            ),
            models.CheckConstraint(
                name="thread_rel_capstone_payload",
                check=(
                    ~models.Q(target_kind=TargetKind.RELATIONSHIP_CAPSTONE)
                    | (
                        models.Q(target_trait__isnull=True)
                        & models.Q(target_technique__isnull=True)
                        & models.Q(target_object__isnull=True)
                        & models.Q(target_relationship_track__isnull=True)
                        & models.Q(target_capstone__isnull=False)
                    )
                ),
            ),
        ]

    def __str__(self) -> str:
        return f"Thread<{self.target_kind}> for {self.owner_id} ({self.resonance_id})"

    @property
    def target(self) -> models.Model | None:
        """Return the populated FK object, picked by target_kind."""
        match self.target_kind:
            case TargetKind.TRAIT:
                return self.target_trait
            case TargetKind.TECHNIQUE:
                return self.target_technique
            case TargetKind.ITEM | TargetKind.ROOM:
                return self.target_object
            case TargetKind.RELATIONSHIP_TRACK:
                return self.target_relationship_track
            case TargetKind.RELATIONSHIP_CAPSTONE:
                return self.target_capstone
        return None

    def clean(self) -> None:
        """Validate exactly-one-target rule + ITEM typeclass registry membership.

        DB constraints catch the same shape errors at write time; ``clean()``
        is the user-facing error path (forms / serializers / tests calling
        ``full_clean()``).
        """
        # Map target_kind -> (expected_field_name, list_of_other_field_names)
        kind_to_field: dict[str, str] = {
            TargetKind.TRAIT: "target_trait",
            TargetKind.TECHNIQUE: "target_technique",
            TargetKind.ITEM: "target_object",
            TargetKind.ROOM: "target_object",
            TargetKind.RELATIONSHIP_TRACK: "target_relationship_track",
            TargetKind.RELATIONSHIP_CAPSTONE: "target_capstone",
        }
        all_target_fields = (
            "target_trait",
            "target_technique",
            "target_object",
            "target_relationship_track",
            "target_capstone",
        )

        expected_field = kind_to_field.get(self.target_kind)
        if expected_field is None:
            raise ValidationError(
                {"target_kind": f"Unknown target_kind: {self.target_kind!r}."},
            )

        if getattr(self, expected_field) is None:
            raise ValidationError(
                {expected_field: f"target_kind={self.target_kind} requires {expected_field}."},
            )

        for field_name in all_target_fields:
            if field_name == expected_field:
                continue
            if getattr(self, field_name) is not None:
                raise ValidationError(
                    {
                        field_name: (
                            f"target_kind={self.target_kind} requires {field_name} to be null."
                        ),
                    },
                )

        # ITEM-kind: validate the target_object's typeclass is in the
        # THREADWEAVING_ITEM_TYPECLASSES registry (subclass-aware).
        if self.target_kind == TargetKind.ITEM:
            from world.magic.services import _typeclass_path_in_registry  # noqa: PLC0415

            tc_path = self.target_object.db_typeclass_path
            if not _typeclass_path_in_registry(tc_path, THREADWEAVING_ITEM_TYPECLASSES):
                raise ValidationError(
                    {
                        "target_object": (
                            f"Typeclass {tc_path!r} is not in "
                            "THREADWEAVING_ITEM_TYPECLASSES registry."
                        ),
                    },
                )


class ThreadLevelUnlock(SharedMemoryModel):
    """Per-thread level-unlock receipt.

    Records that ``thread`` paid ``xp_spent`` to unlock ``unlocked_level`` on the
    internal level scale (multiples of 10). Spec A §2.1 lines 200-206. Pairs
    with ThreadXPLockedLevel (the global price list); a row here represents one
    ownership instance of one boundary on one thread.
    """

    thread = models.ForeignKey(
        Thread,
        on_delete=models.PROTECT,
        related_name="level_unlocks",
        help_text="Thread that purchased this level unlock.",
    )
    unlocked_level = models.PositiveSmallIntegerField(
        help_text="Level boundary unlocked (matches ThreadXPLockedLevel.level).",
    )
    xp_spent = models.PositiveIntegerField(
        help_text="XP actually spent at unlock time (snapshot of price list).",
    )
    acquired_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = (("thread", "unlocked_level"),)
        ordering = ("thread", "unlocked_level")

    def __str__(self) -> str:
        return f"Thread {self.thread_id} -> lvl {self.unlocked_level}"


class ThreadWeavingUnlock(SharedMemoryModel):
    """Authored unlock catalog. Discriminator + typed-FK; one unlock per anchor.

    No name/description: ``display_name`` derives from the discriminator FK
    (Spec A §2.1 lines 348-369). Per-kind partial UniqueConstraints +
    CheckConstraints enforce 'one unlock per anchor' and 'exactly one
    target_* set, matching target_kind' at the DB layer. ``clean()`` mirrors
    the same shape rules at the application layer plus validates ITEM
    typeclass paths against the THREADWEAVING_ITEM_TYPECLASSES registry.

    Spec A §2.1 lines 313-429.
    """

    target_kind = models.CharField(
        max_length=32,
        choices=TargetKind.choices,
        help_text="Discriminator selecting which unlock_* field is populated.",
    )

    unlock_trait = models.ForeignKey(
        "traits.Trait",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="thread_weaving_unlocks",
        help_text="Set when target_kind=TRAIT; null otherwise.",
    )
    unlock_gift = models.ForeignKey(
        "magic.Gift",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="thread_weaving_unlocks",
        help_text="Set when target_kind=TECHNIQUE; covers all techniques under Gift.",
    )
    unlock_item_typeclass_path = models.CharField(
        max_length=255,
        blank=True,
        help_text="Set when target_kind=ITEM; typeclass path string.",
    )
    unlock_room_property = models.ForeignKey(
        "mechanics.Property",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="thread_weaving_unlocks",
        help_text="Set when target_kind=ROOM; rooms with this Property.",
    )
    unlock_track = models.ForeignKey(
        "relationships.RelationshipTrack",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="thread_weaving_unlocks",
        help_text="Set when target_kind=RELATIONSHIP_TRACK; per-track unlock.",
    )

    xp_cost = models.PositiveIntegerField(
        help_text="Base XP cost; multiplied by out_of_path_multiplier when out-of-Path.",
    )
    paths = models.ManyToManyField(
        "classes.Path",
        related_name="thread_weaving_unlocks",
        blank=True,
        help_text="Paths that treat this unlock as in-band (full xp_cost).",
    )
    out_of_path_multiplier = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("2.0"),
        help_text="Cost multiplier applied when buyer's Path is not in `paths`.",
    )

    class Meta:
        constraints = [
            # ---- Per-kind partial UniqueConstraints (one per TargetKind, no CAPSTONE) -
            models.UniqueConstraint(
                fields=["unlock_trait"],
                condition=models.Q(target_kind="TRAIT"),
                name="unique_threadweaving_unlock_trait",
            ),
            models.UniqueConstraint(
                fields=["unlock_gift"],
                condition=models.Q(target_kind="TECHNIQUE"),
                name="unique_threadweaving_unlock_gift",
            ),
            models.UniqueConstraint(
                fields=["unlock_item_typeclass_path"],
                condition=models.Q(target_kind="ITEM"),
                name="unique_threadweaving_unlock_item",
            ),
            models.UniqueConstraint(
                fields=["unlock_room_property"],
                condition=models.Q(target_kind="ROOM"),
                name="unique_threadweaving_unlock_room",
            ),
            models.UniqueConstraint(
                fields=["unlock_track"],
                condition=models.Q(target_kind="RELATIONSHIP_TRACK"),
                name="unique_threadweaving_unlock_track",
            ),
            # ---- Per-kind CheckConstraints (exactly one target_* set, others null) ----
            models.CheckConstraint(
                name="threadweaving_trait_payload",
                check=(
                    ~models.Q(target_kind="TRAIT")
                    | (
                        models.Q(unlock_trait__isnull=False)
                        & models.Q(unlock_gift__isnull=True)
                        & models.Q(unlock_item_typeclass_path="")
                        & models.Q(unlock_room_property__isnull=True)
                        & models.Q(unlock_track__isnull=True)
                    )
                ),
            ),
            models.CheckConstraint(
                name="threadweaving_technique_payload",
                check=(
                    ~models.Q(target_kind="TECHNIQUE")
                    | (
                        models.Q(unlock_trait__isnull=True)
                        & models.Q(unlock_gift__isnull=False)
                        & models.Q(unlock_item_typeclass_path="")
                        & models.Q(unlock_room_property__isnull=True)
                        & models.Q(unlock_track__isnull=True)
                    )
                ),
            ),
            models.CheckConstraint(
                name="threadweaving_item_payload",
                check=(
                    ~models.Q(target_kind="ITEM")
                    | (
                        models.Q(unlock_trait__isnull=True)
                        & models.Q(unlock_gift__isnull=True)
                        & ~models.Q(unlock_item_typeclass_path="")
                        & models.Q(unlock_room_property__isnull=True)
                        & models.Q(unlock_track__isnull=True)
                    )
                ),
            ),
            models.CheckConstraint(
                name="threadweaving_room_payload",
                check=(
                    ~models.Q(target_kind="ROOM")
                    | (
                        models.Q(unlock_trait__isnull=True)
                        & models.Q(unlock_gift__isnull=True)
                        & models.Q(unlock_item_typeclass_path="")
                        & models.Q(unlock_room_property__isnull=False)
                        & models.Q(unlock_track__isnull=True)
                    )
                ),
            ),
            models.CheckConstraint(
                name="threadweaving_track_payload",
                check=(
                    ~models.Q(target_kind="RELATIONSHIP_TRACK")
                    | (
                        models.Q(unlock_trait__isnull=True)
                        & models.Q(unlock_gift__isnull=True)
                        & models.Q(unlock_item_typeclass_path="")
                        & models.Q(unlock_room_property__isnull=True)
                        & models.Q(unlock_track__isnull=False)
                    )
                ),
            ),
            # CAPSTONE has no slot on this model — capstones inherit from their
            # parent RELATIONSHIP_TRACK unlock per spec line 426. The 5
            # per-kind checks above all early-out for non-matching target_kind
            # values, so without this guard a CAPSTONE row with all target_*
            # slots empty would satisfy every check. Forbid it explicitly.
            models.CheckConstraint(
                name="threadweaving_no_capstone",
                check=~models.Q(target_kind="RELATIONSHIP_CAPSTONE"),
            ),
        ]

    # Field-name constants used by clean() / _get_target_value() to dispatch by
    # target_kind. Extracted so the STRING_LITERAL linter doesn't flag bare
    # string field names — and so renaming a target_* field forces a single
    # update here.
    _F_TRAIT = "unlock_trait"
    _F_GIFT = "unlock_gift"
    _F_ITEM_PATH = "unlock_item_typeclass_path"
    _F_ROOM = "unlock_room_property"
    _F_TRACK = "unlock_track"

    # Discriminator -> required field name. CAPSTONE is intentionally absent
    # (capstones inherit from RELATIONSHIP_TRACK unlocks per spec line 426).
    _KIND_TO_FIELD: dict[str, str] = {
        TargetKind.TRAIT: _F_TRAIT,
        TargetKind.TECHNIQUE: _F_GIFT,
        TargetKind.ITEM: _F_ITEM_PATH,
        TargetKind.ROOM: _F_ROOM,
        TargetKind.RELATIONSHIP_TRACK: _F_TRACK,
    }
    _ALL_TARGET_FIELDS: tuple[str, ...] = (
        _F_TRAIT,
        _F_GIFT,
        _F_ITEM_PATH,
        _F_ROOM,
        _F_TRACK,
    )

    def _get_target_value(self, field_name: str) -> object | None:
        """Return the populated value for ``field_name``, normalising "" to None.

        ``unlock_item_typeclass_path`` is a CharField with blank=True (no
        nullable column), so 'empty' is "" not None. Normalising lets the
        clean() and display_name code treat all five target_* slots
        uniformly.
        """
        value = getattr(self, field_name)
        if field_name == self._F_ITEM_PATH and value == "":
            return None
        return value

    @property
    def display_name(self) -> str:
        if self.target_kind == TargetKind.TRAIT:
            return f"ThreadWeaving: {self.unlock_trait.name}"
        if self.target_kind == TargetKind.TECHNIQUE:
            return f"ThreadWeaving: Gift of {self.unlock_gift.name}"
        if self.target_kind == TargetKind.ITEM:
            return f"ThreadWeaving: {self.unlock_item_typeclass_path.rsplit('.', 1)[-1]}"
        if self.target_kind == TargetKind.ROOM:
            return f"ThreadWeaving: {self.unlock_room_property.name} spaces"
        if self.target_kind == TargetKind.RELATIONSHIP_TRACK:
            return f"ThreadWeaving: {self.unlock_track.name} bonds"
        return "ThreadWeaving: <unknown>"  # defensive; unreachable while choices apply

    def __str__(self) -> str:
        return self.display_name

    def clean(self) -> None:
        """Validate exactly-one-target rule + ITEM typeclass-registry membership.

        Mirrors Thread.clean() (see models.py). DB CheckConstraints catch the
        same shape errors at write time; clean() is the user-facing error path
        (forms / serializers / tests calling full_clean()).
        """
        expected_field = self._KIND_TO_FIELD.get(self.target_kind)
        if expected_field is None:
            raise ValidationError(
                {"target_kind": f"Unknown target_kind: {self.target_kind!r}."},
            )

        if self._get_target_value(expected_field) is None:
            raise ValidationError(
                {expected_field: f"target_kind={self.target_kind} requires {expected_field}."},
            )

        for field_name in self._ALL_TARGET_FIELDS:
            if field_name == expected_field:
                continue
            if self._get_target_value(field_name) is not None:
                raise ValidationError(
                    {
                        field_name: (
                            f"target_kind={self.target_kind} requires {field_name} to be empty."
                        ),
                    },
                )

        # ITEM-kind: validate the typeclass path is in the registry
        # (subclass-aware via the same helper Thread.clean() uses).
        if self.target_kind == TargetKind.ITEM:
            from world.magic.services import _typeclass_path_in_registry  # noqa: PLC0415

            tc_path = self.unlock_item_typeclass_path
            if not _typeclass_path_in_registry(tc_path, THREADWEAVING_ITEM_TYPECLASSES):
                raise ValidationError(
                    {
                        "unlock_item_typeclass_path": (
                            f"Typeclass {tc_path!r} is not in "
                            "THREADWEAVING_ITEM_TYPECLASSES registry."
                        ),
                    },
                )


class CharacterThreadWeavingUnlock(SharedMemoryModel):
    """Per-character purchase record for a ThreadWeavingUnlock.

    One row per (character, unlock) — enforced by unique_together. Records the
    actual XP paid (which depends on the buyer's Path: in-band uses ``xp_cost``,
    out-of-band multiplies by ``out_of_path_multiplier``) and optionally the
    teacher who unlocked it. Spec A §2.1 lines 431-440.
    """

    character = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="thread_weaving_unlocks",
        help_text="Character who owns this purchase.",
    )
    unlock = models.ForeignKey(
        ThreadWeavingUnlock,
        on_delete=models.PROTECT,
        related_name="character_purchases",
        help_text="Authored unlock the character purchased.",
    )
    acquired_at = models.DateTimeField(auto_now_add=True)
    xp_spent = models.PositiveIntegerField(
        help_text="Actual XP paid (in-Path: xp_cost; out-of-Path: xp_cost * multiplier).",
    )
    teacher = models.ForeignKey(
        "roster.RosterTenure",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="thread_weaving_unlocks_taught",
        help_text="Teacher RosterTenure when applicable; audit only.",
    )

    class Meta:
        unique_together = (("character", "unlock"),)

    def __str__(self) -> str:
        return f"CharacterThreadWeavingUnlock<{self.character_id} -> {self.unlock_id}>"


class ThreadWeavingTeachingOffer(SharedMemoryModel):
    """Teacher-side offer linking a RosterTenure to a ThreadWeavingUnlock.

    Mirrors the existing CodexTeachingOffer model exactly. NPC academy teachers
    are seeded as RosterTenure-backed offers tied to specific ThreadWeaving
    unlocks. Path multiplier (in-band vs. out-of-band) is computed at acceptance
    time, not stored on the offer. Spec A §4.2 lines 1186-1198.
    """

    teacher = models.ForeignKey(
        "roster.RosterTenure",
        on_delete=models.CASCADE,
        related_name="thread_weaving_offers",
        help_text="Teaching tenure offering this unlock.",
    )
    unlock = models.ForeignKey(
        ThreadWeavingUnlock,
        on_delete=models.PROTECT,
        related_name="teaching_offers",
        help_text="Authored unlock being offered.",
    )
    pitch = models.TextField(
        help_text="Teacher's narrative pitch for this offer.",
    )
    gold_cost = models.PositiveIntegerField(
        default=0,
        help_text="Gold price the teacher charges (XP cost stays on the unlock).",
    )
    banked_ap = models.PositiveIntegerField(
        help_text="Teacher's AP commitment backing this offer.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"ThreadWeavingTeachingOffer<{self.teacher_id} -> {self.unlock_id}>"


from world.magic.audere import AudereThreshold  # noqa: F401, E402
