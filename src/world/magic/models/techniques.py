"""Techniques: player-created magical abilities and their building blocks.

EffectType / TechniqueStyle / Restriction / IntensityTier are lookup tables.
Technique is the player-created ability; TechniqueCapabilityGrant ties a
technique to a conditions.Capability with intensity-scaled value.
CharacterTechnique links a character to a known technique.
TechniqueOutcomeModifier maps technique check outcomes to Soulfray resilience
modifiers.
TechniqueAppliedCondition is an authored through-model binding a Technique to a
ConditionTemplate with formula-based severity/duration scaling.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils.functional import cached_property
from evennia.utils.idmapper.models import SharedMemoryModel

from actions.constants import ActionCategory, ActionTargetType
from core.managers import CachedAllMixin
from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.achievements.models import DiscoverableContent
from world.covenants.constants import RoleArchetype
from world.magic.constants import TechniqueCategory, TechniqueFunction, TechniqueReach
from world.magic.models.gifts import Gift

# App-qualified model paths repeated across FK references; centralized for dedup.
_TECHNIQUE_MODEL = "magic.Technique"
_CONDITION_TEMPLATE_MODEL = "conditions.ConditionTemplate"
_CAPABILITY_TYPE_MODEL = "conditions.CapabilityType"


class ConditionTargetKind(models.TextChoices):
    """Who a condition applied by a technique targets."""

    SELF = "self", "Self"
    ALLY = "ally", "Ally"
    ENEMY = "enemy", "Enemy"


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
    category = models.CharField(
        max_length=16,
        choices=TechniqueCategory.choices,
        default=TechniqueCategory.UTILITY,
        help_text=(
            "Player-facing grouping (Offense/Defense/...) for CG and category-keyed modifiers."
        ),
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


class IntensityTierManager(CachedAllMixin, NaturalKeyManager):
    """Manager for IntensityTier with natural key support, plus cached_all() (#1846)."""


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

    objects = IntensityTierManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        ordering = ["threshold"]
        verbose_name = "Intensity Tier"
        verbose_name_plural = "Intensity Tiers"

    def __str__(self) -> str:
        return f"{self.name} (threshold: {self.threshold})"


class TechniqueManager(NaturalKeyManager):
    """Manager for Technique with natural key support (#2474/#2486).

    Keyed ``(gift, name)`` rather than ``name`` alone: ``name`` is not unique
    on its own (different gifts can reuse a technique name). Within one Gift
    the pair is DB-unique (``unique_technique_gift_name``).
    """


class Technique(NaturalKeyMixin, DiscoverableContent, SharedMemoryModel):
    """
    A specific magical ability within a Gift.

    Techniques represent magical abilities with intensity (raw power) and control
    (safety/precision). When intensity exceeds control at runtime, effects become
    unpredictable and anima cost can spike. Level gates progression and derives tier.
    A staff-authored catalog table (post-#2426): techniques belong to a Gift, not to
    an individual character, and are shared across every character who knows the Gift.
    """

    name = models.CharField(
        max_length=200,
        help_text="Name of the technique (unique within its gift).",
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
    enhances_effect_type = models.ForeignKey(
        EffectType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="enhanced_by_techniques",
        help_text=(
            "#2022: If set, this is an enhancement technique — it boosts "
            "techniques whose effect_type matches this field rather than "
            "being a standalone cast. Role-granted gifts primarily carry "
            "enhancement techniques so a well-matched vow amplifies existing "
            "kit instead of competing with it. Null = standalone technique."
        ),
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
    action_category = models.CharField(
        max_length=10,
        choices=ActionCategory.choices,
        default=ActionCategory.PHYSICAL,
        help_text=(
            "Physical/social/mental arena this technique acts in "
            "(drives combat slot + fatigue routing)."
        ),
    )
    archetype_alignment = models.CharField(
        max_length=20,
        choices=RoleArchetype.choices,
        default=RoleArchetype.CROWN,
        help_text=(
            "#2529: which SWORD/SHIELD/CROWN blend axis boosts this technique "
            "(designer-authored; seeded from effect_type.category, override for "
            "edge cases like a self-damage-buff→SWORD)."
        ),
    )
    reach = models.CharField(
        max_length=20,
        choices=TechniqueReach.choices,
        default=TechniqueReach.ANY,
        help_text=(
            "Positional reach: which positions this technique can target "
            "(SAME=melee, ADJACENT=reach, ANY=ranged)."
        ),
    )
    reach_hops = models.PositiveSmallIntegerField(
        default=1,
        help_text=(
            "When reach=REACH_N, the maximum number of passable edges "
            "BFS may traverse. Ignored for SAME/ADJACENT/ANY."
        ),
    )
    target_type = models.CharField(
        max_length=20,
        choices=ActionTargetType.choices,
        default=ActionTargetType.SINGLE,
        help_text=(
            "Per-technique target cardinality (how many / how selected). "
            "Relationship (self/ally/enemy) is derived from condition target_kinds "
            "+ hostility, not stored here."
        ),
    )
    combo_opening_probing = models.PositiveIntegerField(
        null=True,
        blank=True,
        default=None,
        help_text=(
            "If set, this technique used as a passive grants this much probing to "
            "engaged opponents when it resolves (feeds combo minimum_probing). "
            "None means the technique is not a combo-opening passive."
        ),
    )
    anima_cost = models.PositiveIntegerField(
        help_text="Anima cost to use this technique.",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of what this technique does.",
    )
    # === Clash fields (Task 1.5) ===
    clash_capable = models.BooleanField(
        default=False,
        help_text=(
            "When True, this technique can be committed as a clash action. "
            "Drives clash-opportunity detection."
        ),
    )
    clash_resolution_pool = models.ForeignKey(
        "actions.ConsequencePool",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text=(
            "Resolution consequence pool for clashes opened by this technique "
            "(CLASH or LOCK/Suppress). Null when no clash opens via this technique."
        ),
    )
    clash_per_round_pool = models.ForeignKey(
        "actions.ConsequencePool",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text=(
            "Per-round incremental-feedback pool for clashes opened by this technique. "
            "Null when no per-round feedback is authored."
        ),
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
    applied_conditions = models.ManyToManyField(
        _CONDITION_TEMPLATE_MODEL,
        through="magic.TechniqueAppliedCondition",
        related_name="techniques_applying",
        blank=True,
        help_text="Conditions this technique can apply, with formula-based scaling.",
    )
    properties = models.ManyToManyField(
        "mechanics.Property",
        related_name="techniques",
        blank=True,
        help_text="Neutral descriptive tags on this technique (e.g. cursed), used by "
        "reactive trigger filters via the has_property op.",
    )
    target_prerequisites = models.ManyToManyField(
        "mechanics.Prerequisite",
        related_name="gated_techniques",
        blank=True,
        help_text="Property-based targeting preconditions a target must satisfy "
        "(ALL must pass) to be a legal target for this technique.",
    )
    target_weather_type = models.ForeignKey(
        "weather.WeatherType",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conjuring_techniques",
        help_text="For SET_ENVIRONMENT battle actions (#1715): which WeatherType this "
        "cast conjures when successfully declared as a battle environmental effect. "
        "Null on every non-environmental technique.",
    )
    travel_anchor_kind = models.ForeignKey(
        "magic.PortalAnchorKind",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="travel_techniques",
        help_text="Set = this technique is a portal-travel technique through this "
        "anchor medium (#2222).",
    )
    codex_entry = models.ForeignKey(
        "codex.CodexEntry",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="techniques",
        help_text="Lore entry this technique is bound to, if any.",
    )

    objects = TechniqueManager()

    class NaturalKeyConfig:
        fields = ["gift", "name"]
        dependencies = ["magic.Gift"]

    class Meta:
        verbose_name = "Technique"
        verbose_name_plural = "Techniques"
        constraints = [
            models.UniqueConstraint(
                fields=["gift", "name"],
                name="unique_technique_gift_name",
            ),
        ]

    def clean(self) -> None:
        """Validate reach_hops is meaningful when reach=REACH_N."""
        super().clean()
        if self.reach == TechniqueReach.REACH_N and self.reach_hops < 1:
            msg = "reach_hops must be >= 1 when reach is REACH_N."
            raise ValidationError({"reach_hops": msg})

    @cached_property
    def cached_restrictions(self) -> list:
        """Restrictions for this technique. Supports Prefetch(to_attr=)."""
        return list(self.restrictions.all())

    @cached_property
    def cached_variants(self) -> list:
        """Resonance-specialized variants of this technique. Supports Prefetch(to_attr=).

        Read by the shared specialization engine's ``_variant_queryset``
        (via list-comp filter) rather than ``.variants.filter()`` per project
        cached-property rule. To invalidate: ``del instance.cached_variants``.
        """
        return list(self.variants.all())

    @cached_property
    def cached_damage_profiles(self) -> list:
        """Damage profiles for this technique. Supports Prefetch(to_attr=).

        To invalidate: ``del instance.cached_damage_profiles``.
        """
        return list(self.damage_profiles.all())

    @cached_property
    def cached_capability_grants(self) -> list:
        """Capability grants for this technique. Supports Prefetch(to_attr=).

        To invalidate: ``del instance.cached_capability_grants``.
        """
        return list(self.capability_grants.all())

    @cached_property
    def cached_condition_applications(self) -> list:
        """Applied conditions for this technique. Supports Prefetch(to_attr=).

        To invalidate: ``del instance.cached_condition_applications``.
        """
        return list(self.condition_applications.all())

    @cached_property
    def cached_removed_conditions(self) -> list:
        """Removed conditions (dispel payloads) for this technique. Supports Prefetch.

        To invalidate: ``del instance.cached_removed_conditions``.
        """
        return list(self.removed_conditions.all())

    @cached_property
    def cached_target_prerequisites(self) -> list:
        """Targeting preconditions for this technique. Supports Prefetch(to_attr=).

        To invalidate: ``del instance.cached_target_prerequisites``.
        """
        return list(self.target_prerequisites.all())

    @cached_property
    def cached_function_tags(self) -> list:
        """Fine-grained TechniqueFunction labels for this technique (#2443).

        Supports Prefetch(to_attr=). To invalidate: ``del instance.cached_function_tags``.
        """
        return list(self.function_tags.all())

    def has_property(self, name: str) -> bool:
        """Return True if this technique carries the named Property tag."""
        return self.properties.filter(name=name).exists()

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

    @cached_property
    def is_lock_applying(self) -> bool:
        """Return True if this technique applies any ConditionTemplate flagged as a clash-lock.

        The technique's applied conditions are reachable via condition_applications
        (TechniqueAppliedCondition through model). Returns False when no lock-flagged
        condition is found.
        """
        return self.condition_applications.filter(condition__is_clash_lock=True).exists()


class TechniqueFunctionTagManager(NaturalKeyManager):
    """Natural-key manager for TechniqueFunctionTag."""


class TechniqueFunctionTag(NaturalKeyMixin, SharedMemoryModel):
    """One fine-grained function label carried by a technique (#2443).

    Content row (lore repo): links a Technique to a TechniqueFunction value.
    A technique may carry several (a damage+weaken cast carries WEAKEN).
    Consumed by per-vow specialties (#2443) and situational perks (#2536).
    """

    technique = models.ForeignKey(
        Technique,
        on_delete=models.CASCADE,
        related_name="function_tags",
    )
    function = models.CharField(max_length=32, choices=TechniqueFunction.choices)

    objects = TechniqueFunctionTagManager()

    class Meta:
        ordering = ["technique__name", "function"]
        constraints = [
            models.UniqueConstraint(
                fields=["technique", "function"],
                name="unique_function_per_technique",
            ),
        ]

    class NaturalKeyConfig:
        fields = ["technique", "function"]

    def __str__(self) -> str:
        return f"{self.technique.name}: {self.get_function_display()}"


class AbstractCapabilityGrant(SharedMemoryModel):
    """Abstract base holding the shared data columns for capability-grant payload rows.

    Concrete subclasses (TechniqueCapabilityGrant and the forthcoming TechniqueDraftCapabilityGrant)
    each add their own owner FK, prerequisite FK, and any UniqueConstraints.
    """

    capability = models.ForeignKey(
        _CAPABILITY_TYPE_MODEL,
        on_delete=models.CASCADE,
        related_name="%(class)s_grants",
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

    class Meta:
        abstract = True


class AbstractAppliedCondition(SharedMemoryModel):
    """Abstract base holding the shared data columns for applied-condition payload rows.

    Concrete subclasses add their own owner FK, UniqueConstraints, and compute methods.
    """

    condition = models.ForeignKey(
        _CONDITION_TEMPLATE_MODEL,
        on_delete=models.PROTECT,
        related_name="%(class)s_applied",
    )
    target_kind = models.CharField(
        max_length=16,
        choices=ConditionTargetKind.choices,
        default=ConditionTargetKind.ENEMY,
    )
    minimum_success_level = models.PositiveIntegerField(
        default=1,
        help_text="Minimum success level required to apply this condition.",
    )

    base_severity = models.PositiveIntegerField(
        default=1,
        help_text="Flat base severity applied when the condition triggers.",
    )
    severity_intensity_multiplier = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal(0),
        help_text="Multiplied by effective_power and added to severity.",
    )
    severity_per_extra_sl = models.PositiveIntegerField(
        default=0,
        help_text="Extra severity added per success level above the minimum.",
    )

    base_duration_rounds = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "Base duration in rounds. When null, falls back to condition.default_duration_value."
        ),
    )
    duration_intensity_multiplier = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal(0),
        help_text="Multiplied by effective_power and added to duration.",
    )
    duration_per_extra_sl = models.PositiveIntegerField(
        default=0,
        help_text="Extra duration rounds added per success level above the minimum.",
    )

    stack_count = models.PositiveIntegerField(
        default=1,
        help_text="Number of condition stacks applied when triggered.",
    )

    class Meta:
        abstract = True

    def compute_severity(
        self,
        *,
        effective_power: int,
        success_level: int,
    ) -> int:
        """Return the severity to apply at the given power and success level.

        Severity formula:
            base_severity + floor(severity_intensity_multiplier * effective_power)
                + severity_per_extra_sl * max(0, success_level - minimum_success_level)
        """
        return _scale_by_power_and_sl(
            self.base_severity,
            self.severity_intensity_multiplier,
            effective_power,
            self.severity_per_extra_sl,
            success_level,
            self.minimum_success_level,
        )

    def compute_duration_rounds(
        self,
        *,
        effective_power: int,
        success_level: int,
    ) -> int | None:
        """Return the duration in rounds, falling back to condition.default_duration_value.

        Shared by every concrete payload subclass (Technique / TechniqueVariant /
        TechniqueDraft / SignatureMotifBonus) so the apply seam can read the same
        formula off any applied-condition row.
        """
        base = self.base_duration_rounds
        if base is None:
            base = self.condition.default_duration_value
        return _scale_by_power_and_sl(
            base,
            self.duration_intensity_multiplier,
            effective_power,
            self.duration_per_extra_sl,
            success_level,
            self.minimum_success_level,
        )


class AbstractDamageProfile(SharedMemoryModel):
    """Abstract base holding the shared data columns for damage-profile payload rows.

    Concrete subclasses add their own owner FK, UniqueConstraints, and compute methods.
    """

    damage_type = models.ForeignKey(
        "conditions.DamageType",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="%(class)s_damage_profiles",
        help_text="Damage type for resistance lookup. Null = untyped damage.",
    )
    minimum_success_level = models.PositiveIntegerField(default=1)

    base_damage = models.PositiveIntegerField(default=0)
    damage_intensity_multiplier = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal(0),
    )
    damage_per_extra_sl = models.PositiveIntegerField(default=0)
    uses_equipped_weapon = models.BooleanField(
        default=False,
        help_text=(
            "When True, the wielder's equipped-weapon effective damage is added "
            "to this profile's budget and its damage_type fills in when null."
        ),
    )
    execute_missing_health_multiplier = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal(0),
        help_text=(
            "Smooth execute ramp (#2643): the resolving hit's damage is scaled by "
            "1 + this * missing_health_fraction, computed off the target's PRE-hit "
            "health (never recursive). Default 0 is a no-op — most techniques don't "
            "execute; Strike-family techniques opt in via authored data. Applied at "
            "both damage seams (world.combat.services.apply_damage_to_opponent / "
            "apply_damage_to_participant)."
        ),
    )

    def compute_damage_budget(
        self,
        *,
        effective_power: int,
        success_level: int,
    ) -> int:
        """Per-formula damage value before SL multiplier and soak."""
        return _scale_by_power_and_sl(
            self.base_damage,
            self.damage_intensity_multiplier,
            effective_power,
            self.damage_per_extra_sl,
            success_level,
            self.minimum_success_level,
        )

    class Meta:
        abstract = True


class TechniqueCapabilityGrant(NaturalKeyMixin, AbstractCapabilityGrant):
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
    prerequisite = models.ForeignKey(
        "mechanics.Prerequisite",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="technique_grants",
        help_text="Source-specific prerequisite, checked in addition to Capability-level ones.",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["technique", "capability"]
        dependencies = [_TECHNIQUE_MODEL, _CAPABILITY_TYPE_MODEL]

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["technique", "capability"],
                name="technique_capability_grant_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.technique.name} grants {self.capability.name}"

    def calculate_value(
        self,
        *,
        effective_power: int | None = None,
    ) -> int:
        """Calculate effective Capability value.

        effective_power: when provided (e.g., from combat where pull bumps
        may apply), uses that aggregate. When None (out-of-combat challenges
        or no combat context), falls back to self.technique.intensity.
        """
        power = effective_power if effective_power is not None else self.technique.intensity
        return int(self.base_value + (self.intensity_multiplier * Decimal(power)))


class TechniqueCapabilityRequirement(NaturalKeyMixin, SharedMemoryModel):
    """A capability a character must possess (at >= minimum_value) to perform
    this Technique. Evaluated against get_effective_capability_value. Example:
    a two-handed strike requires limb_use >= 2; nearly all techniques require
    awareness >= 1.
    """

    technique = models.ForeignKey(
        _TECHNIQUE_MODEL,
        on_delete=models.CASCADE,
        related_name="capability_requirements",
    )
    capability = models.ForeignKey(
        _CAPABILITY_TYPE_MODEL,
        on_delete=models.CASCADE,
        related_name="technique_requirements",
    )
    minimum_value = models.PositiveIntegerField(
        default=1,
        help_text="Minimum effective capability value required. 1 = presence.",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["technique", "capability"]
        dependencies = [_TECHNIQUE_MODEL, _CAPABILITY_TYPE_MODEL]

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["technique", "capability"],
                name="technique_capability_requirement_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.technique.name} requires {self.capability.name} >= {self.minimum_value}"


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
    source = models.ForeignKey(
        "mechanics.ModifierSource",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="granted_techniques",
        help_text=(
            "If set, this technique is GRANTED by a modifier source (e.g. an active "
            "alternate self's ability-suite) and is deleted when that source's rows are "
            "cleaned up. Null = permanently learned."
        ),
    )
    role_source = models.ForeignKey(
        "covenants.CharacterCovenantRole",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="granted_techniques",
        help_text=(
            "#2022: If set, this technique was auto-granted by an engaged covenant "
            "role's granted_gifts. Auto-revoked when the role disengages (the #2051 "
            "vow-dim path). Null = permanently learned or granted by another source."
        ),
    )

    class Meta:
        unique_together = ["character", "technique"]
        verbose_name = "Character Technique"
        verbose_name_plural = "Character Techniques"

    def __str__(self) -> str:
        return f"{self.technique} on {self.character}"


class TechniqueOutcomeModifier(NaturalKeyMixin, SharedMemoryModel):
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

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["outcome"]
        dependencies = ["traits.CheckOutcome"]

    class Meta:
        verbose_name = "Technique Outcome Modifier"
        verbose_name_plural = "Technique Outcome Modifiers"

    def __str__(self) -> str:
        sign = "+" if self.modifier_value >= 0 else ""
        return f"{self.outcome}: {sign}{self.modifier_value} to resilience"


def _scale_by_power_and_sl(  # noqa: PLR0913
    base: int,
    multiplier: Decimal,
    effective_power: int,
    per_extra_sl: int,
    success_level: int,
    minimum_success_level: int,
) -> int:
    """Shared scaling formula: base + floor(multiplier * power) + per_sl * max(0, sl - min_sl)."""
    power_contribution = int(multiplier * effective_power)
    sl_above = max(0, success_level - minimum_success_level)
    return base + power_contribution + per_extra_sl * sl_above


class TechniqueAppliedCondition(NaturalKeyMixin, AbstractAppliedCondition):
    """Authored row binding a Technique to a ConditionTemplate with formula-based
    severity / duration scaling. One Technique may have many of these.

    Severity formula:
        base_severity + floor(severity_intensity_multiplier * effective_power)
            + severity_per_extra_sl * max(0, success_level - minimum_success_level)

    Duration formula (falls back to condition.default_duration_value when base_duration_rounds
    is None):
        base + floor(duration_intensity_multiplier * effective_power)
            + duration_per_extra_sl * max(0, success_level - minimum_success_level)
    """

    technique = models.ForeignKey(
        Technique,
        on_delete=models.CASCADE,
        related_name="condition_applications",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["technique", "condition", "target_kind"]
        dependencies = [_TECHNIQUE_MODEL, _CONDITION_TEMPLATE_MODEL]

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["technique", "condition", "target_kind"],
                name="unique_applied_condition_per_technique",
            ),
        ]
        verbose_name = "Technique Applied Condition"
        verbose_name_plural = "Technique Applied Conditions"

    def __str__(self) -> str:
        return f"{self.technique.name} → {self.condition.name} ({self.target_kind})"


class TechniqueRemovedCondition(NaturalKeyMixin, AbstractAppliedCondition):
    """Authored row binding a Technique to a ConditionTemplate it *removes* on cast.

    Mirrors ``TechniqueAppliedCondition`` but for dispel/cleanse: when the technique
    is cast, each row strips the named condition from the resolved target. The
    severity / duration / stack-count knobs inherited from ``AbstractAppliedCondition``
    are inert for removal — ``clean()`` enforces they stay at defaults. The one
    removal-specific field is ``remove_all_stacks`` (forwarded to
    ``remove_condition(remove_all_stacks=...)``).

    A condition whose template has ``can_be_dispelled=False`` is a no-op (hard gate).
    When ``cure_check_type`` is set on the condition template, an opposed
    ``perform_check`` is rolled before removal (#1585).
    """

    technique = models.ForeignKey(
        Technique,
        on_delete=models.CASCADE,
        related_name="removed_conditions",
    )
    remove_all_stacks = models.BooleanField(
        default=True,
        help_text=(
            "If True, all stacks of the condition are removed. If False, only one "
            "stack is decremented (the condition persists with stacks - 1)."
        ),
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["technique", "condition", "target_kind"]
        dependencies = [_TECHNIQUE_MODEL, _CONDITION_TEMPLATE_MODEL]

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["technique", "condition", "target_kind"],
                name="unique_removed_condition_per_technique",
            ),
        ]
        verbose_name = "Technique Removed Condition"
        verbose_name_plural = "Technique Removed Conditions"

    def __str__(self) -> str:
        return f"{self.technique.name} → removes {self.condition.name} ({self.target_kind})"

    def clean(self) -> None:
        """Enforce that inert apply-only knobs stay at their defaults.

        Severity, duration, and stack_count are meaningless for removal — a removal
        row deletes (or decrements) a condition instance; it does not apply one.
        Keeping these at defaults prevents authored-but-inert data from misleading
        the budget pricer or future readers.
        """
        super().clean()
        # Inert apply-only knobs must stay at defaults (removal neither applies
        # severity/duration nor stacks). Defined as (field, expected, label) tuples
        # so the check stays a single loop instead of seven near-identical blocks.
        inert_defaults: list[tuple[str, object, str]] = [
            ("base_severity", 1, "Severity is inert for a removal row; leave at default 1."),
            ("severity_intensity_multiplier", Decimal(0), "Inert for a removal row; leave at 0."),
            ("severity_per_extra_sl", 0, "Inert for a removal row; leave at 0."),
            ("base_duration_rounds", None, "Duration is inert for a removal row; leave null."),
            ("duration_intensity_multiplier", Decimal(0), "Inert for a removal row; leave at 0."),
            ("duration_per_extra_sl", 0, "Inert for a removal row; leave at 0."),
            ("stack_count", 1, "Stack count is inert for a removal row; leave at default 1."),
        ]
        for field_name, expected, message in inert_defaults:
            if getattr(self, field_name) != expected:
                raise ValidationError({field_name: message})


class TechniqueTreatment(NaturalKeyMixin, SharedMemoryModel):
    """Authored row binding a Technique to a TreatmentTemplate it performs on cast.

    When the technique is cast, each row whose minimum_success_level is met
    attempts to perform the linked TreatmentTemplate on each resolved target
    that carries the treatment's target condition. The treatment runs its own
    internal check roll and enforces all bounded-mend gates (per-healer-once,
    never-to-full fraction, costs, TreatmentAttempt record) via perform_treatment.

    The engagement gate is skipped for technique-cast treatments (magical
    treatment works in combat); the scene gate still applies.
    """

    technique = models.ForeignKey(
        Technique,
        on_delete=models.CASCADE,
        related_name="treatments",
    )
    treatment_template = models.ForeignKey(
        "conditions.TreatmentTemplate",
        on_delete=models.PROTECT,
        related_name="technique_payloads",
    )
    target_kind = models.CharField(
        max_length=16,
        choices=ConditionTargetKind.choices,
        default=ConditionTargetKind.ALLY,
    )
    minimum_success_level = models.PositiveIntegerField(
        default=1,
        help_text="Minimum success level required to perform this treatment.",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["technique", "treatment_template"]
        dependencies = [_TECHNIQUE_MODEL, "conditions.TreatmentTemplate"]

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["technique", "treatment_template"],
                name="unique_treatment_per_technique",
            ),
        ]
        verbose_name = "Technique Treatment"
        verbose_name_plural = "Technique Treatments"

    def __str__(self) -> str:
        return f"{self.technique.name} → treats {self.treatment_template.name} ({self.target_kind})"


class TechniqueDamageProfile(NaturalKeyMixin, AbstractDamageProfile):
    """One damage component a technique deals when used in combat.

    A technique can have multiple rows for multi-component damage
    (e.g., a slashing fire sword: one slashing row + one fire row).
    Each row scales independently and applies as a separate damage
    event on the target.
    """

    technique = models.ForeignKey(
        Technique,
        on_delete=models.CASCADE,
        related_name="damage_profiles",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["technique", "damage_type"]
        dependencies = [_TECHNIQUE_MODEL, "conditions.DamageType"]

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["technique", "damage_type"],
                condition=Q(damage_type__isnull=False),
                name="unique_damage_profile_per_technique_per_type",
            ),
            models.UniqueConstraint(
                fields=["technique"],
                condition=Q(damage_type__isnull=True),
                name="unique_untyped_damage_profile_per_technique",
            ),
        ]

    def __str__(self) -> str:
        type_str = self.damage_type.name if self.damage_type else "untyped"
        return f"{self.technique.name} → {self.base_damage} {type_str}"
