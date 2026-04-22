"""Techniques: player-created magical abilities and their building blocks.

EffectType / TechniqueStyle / Restriction / IntensityTier are lookup tables.
Technique is the player-created ability; TechniqueCapabilityGrant ties a
technique to a conditions.Capability with intensity-scaled value.
CharacterTechnique links a character to a known technique.
TechniqueOutcomeModifier maps technique check outcomes to Soulfray resilience
modifiers.
"""

from decimal import Decimal
from functools import cached_property

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.magic.models.gifts import Gift


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
