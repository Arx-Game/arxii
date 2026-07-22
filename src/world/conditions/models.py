"""
Conditions System Models

Conditions are persistent states on targets (characters, objects, rooms) that
modify capabilities, checks, and resistances. They can progress through stages,
interact with damage types, and interact with other conditions.

Design doc: docs/plans/2026-01-25-conditions-models-design.md
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from django.db import models
from django.db.models import Q
from django.utils.functional import cached_property
from evennia.utils.idmapper.models import SharedMemoryModel

from core.managers import CachedAllMixin
from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.conditions.constants import (
    ConditionInteractionOutcome,
    ConditionInteractionTrigger,
    DamageTickTiming,
    DurationType,
    StackBehavior,
    TreatmentTargetKind,
)
from world.conditions.types import AdvancementResistFailureKind

if TYPE_CHECKING:
    from world.conditions.handlers import ConditionTemplateReactiveHandler

# FK string constants reused across many fields / NaturalKeyConfig dependency
# lists below. Centralized to avoid the duplicated-literal SonarCloud smell
# (python:S1192).
_CONSEQUENCE_POOL_FK = "actions.ConsequencePool"
_CONDITION_TEMPLATE_FK = "conditions.ConditionTemplate"
_CONDITION_STAGE_FK = "conditions.ConditionStage"

# =============================================================================
# Lookup Tables (SharedMemoryModel - cached, rarely change)
# =============================================================================


class ConditionCategory(NaturalKeyMixin, SharedMemoryModel):
    """
    High-level condition groupings.

    Examples: damage-over-time, debuff, buff, control, poison, environmental
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    display_order = models.PositiveIntegerField(default=0)

    is_negative = models.BooleanField(
        default=True,
        help_text="Are conditions in this category generally harmful?",
    )

    alters_behavior = models.BooleanField(
        default=False,
        help_text=(
            "Conditions in this category change how a character BEHAVES "
            "(compulsion, charm, fear) rather than only their capabilities/stats. "
            "Behavior-altering effects on another PC require that PC's consent."
        ),
    )

    grants_intangibility = models.BooleanField(
        default=False,
        help_text=(
            "Conditions in this category make the bearer untargetable (incorporeal, "
            "sunk, phased). Aggregated by is_untargetable()."
        ),
    )

    conceals_from_perception = models.BooleanField(
        default=False,
        help_text=(
            "Conditions in this category make the bearer imperceptible to others "
            "(invisibility, magical concealment, stealth). Aggregated by is_concealed()."
        ),
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name_plural = "Condition Categories"

    def __str__(self) -> str:
        return self.name

    @cached_property
    def cached_conditions(self) -> list[ConditionTemplate]:
        """Fallback for Prefetch(..., to_attr='cached_conditions').

        When prefetched, Django populates this directly. When accessed without
        prefetch, falls back to a fresh query.
        """
        return list(self.conditions.all())


class CapabilityTypeManager(CachedAllMixin, NaturalKeyManager):
    """Manager for CapabilityType with natural key support, plus cached_all() (#1871)."""


class CapabilityType(NaturalKeyMixin, SharedMemoryModel):
    """
    Capabilities that can be restricted or enhanced by conditions.

    Examples: movement, speech, fine_manipulation, perception,
              magic_use, melee_attack, ranged_attack, concentration
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    innate_baseline = models.IntegerField(
        default=0,
        help_text=(
            "Default value every character has for this capability before "
            "modifiers/conditions. Foundational capacities (awareness, movement, "
            "limb_use) set this >= 1; granted/specialty capabilities leave it 0."
        ),
    )
    prerequisite = models.ForeignKey(
        "mechanics.Prerequisite",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="capability_types",
        help_text="Capability-level prerequisite checked for ALL sources of this Capability.",
    )

    objects = CapabilityTypeManager()

    class NaturalKeyConfig:
        fields = ["name"]

    def __str__(self) -> str:
        return self.name


class DamageType(NaturalKeyMixin, SharedMemoryModel):
    """
    Types of damage that can be dealt or resisted.

    Examples: fire, cold, lightning, acid, poison, shadow,
              force, sound, radiant, psychic, abyssal, witchfire
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    # Link to magic resonance if applicable (one resonance = one damage type)
    resonance = models.OneToOneField(
        "magic.Resonance",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="damage_type",
        help_text="Associated magical resonance, if any",
    )

    # Display
    color_hex = models.CharField(
        max_length=7,
        blank=True,
        help_text="Hex color for UI display (e.g., #FF4400 for fire)",
    )
    icon = models.CharField(max_length=100, blank=True)

    # Consequence pools — nullable so a fallback config default can apply
    wound_pool = models.ForeignKey(
        _CONSEQUENCE_POOL_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="wound_pool_damage_types",
        help_text="Permanent-wound pool for this damage type. Null = use config default.",
    )
    death_pool = models.ForeignKey(
        _CONSEQUENCE_POOL_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="death_pool_damage_types",
        help_text="Tiered death consequences for this damage type. Null → config default.",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    def __str__(self) -> str:
        return self.name


# =============================================================================
# Condition Templates
# =============================================================================


class ConditionTemplate(NaturalKeyMixin, SharedMemoryModel):
    """
    Definition of a condition type.

    Examples: Burning, Frozen, Paralyzed, Poisoned (Paralytic),
              Empowered, Vulnerable, Channeling, Opening
    """

    name = models.CharField(max_length=100, unique=True)
    category = models.ForeignKey(
        ConditionCategory,
        on_delete=models.PROTECT,
        related_name="conditions",
    )
    description = models.TextField(blank=True)

    # What players see when they have this condition
    player_description = models.TextField(
        blank=True,
        help_text="Narrative description shown to the affected player",
    )
    # What others see
    observer_description = models.TextField(
        blank=True,
        help_text="Description shown to others observing the affected target",
    )

    # === Duration Settings ===
    default_duration_type = models.CharField(
        max_length=20,
        choices=DurationType.choices,
        default=DurationType.ROUNDS,
    )
    default_duration_value = models.PositiveIntegerField(
        default=3,
        help_text="Number of rounds if duration_type is 'rounds'",
    )

    # How many difficulty tiers EASIER checks against the bearer resolve while
    # this condition is active (#1697): the "exploitable state" seam — Smitten
    # eases social/scene actions rolled at its bearer by 2 tiers (PLACEHOLDER).
    # 0 (the default) means the condition never eases anything. Consumed by
    # world.scenes.social_difficulty.resolved_base_difficulty.
    exploitable_tiers = models.PositiveSmallIntegerField(
        default=0,
        help_text=(
            "Difficulty tiers checks against the bearer are eased by while this "
            "condition is active (0 = never eases; Smitten uses 2, PLACEHOLDER)."
        ),
    )

    # === Stacking Settings ===
    is_stackable = models.BooleanField(
        default=False,
        help_text="Can multiple instances stack on the same target?",
    )
    max_stacks = models.PositiveIntegerField(
        default=1,
        help_text="Maximum stacks if stackable",
    )

    stack_behavior = models.CharField(
        max_length=20,
        choices=StackBehavior.choices,
        default=StackBehavior.INTENSITY,
        help_text="What stacking affects",
    )

    # === Progression Settings ===
    has_progression = models.BooleanField(
        default=False,
        help_text="Does this condition progress through stages?",
    )

    # === Removal Settings ===
    can_be_dispelled = models.BooleanField(
        default=True,
        help_text="Can magical dispel effects remove this?",
    )
    cure_check_type = models.ForeignKey(
        "checks.CheckType",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cures_conditions",
        help_text="Check type used to cure this condition, if any",
    )
    cure_difficulty = models.PositiveIntegerField(
        default=10,
        help_text="Base difficulty to cure via check",
    )
    resist_check_type = models.ForeignKey(
        "checks.CheckType",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resists_condition_applications",
        help_text="Check type the target rolls to resist this condition being "
        "applied, if any. Null = unconditional application.",
    )
    resist_difficulty = models.PositiveIntegerField(
        default=10,
        help_text="Base difficulty for the target's resist check.",
    )

    # === Combat Relevance ===
    affects_turn_order = models.BooleanField(
        default=False,
        help_text="Does this condition affect initiative/turn order?",
    )
    turn_order_modifier = models.IntegerField(
        default=0,
        help_text="Modifier to turn order (positive = act earlier)",
    )
    draws_aggro = models.BooleanField(
        default=False,
        help_text="Does this condition make the target a priority for enemies?",
    )
    aggro_priority = models.PositiveIntegerField(
        default=0,
        help_text="Higher = more likely to be targeted",
    )

    # === Display Settings ===
    icon = models.CharField(
        max_length=100,
        blank=True,
        help_text="Icon identifier for frontend",
    )
    color_hex = models.CharField(
        max_length=7,
        blank=True,
        help_text="Hex color for UI (e.g., #FF0000)",
    )
    display_priority = models.PositiveIntegerField(
        default=0,
        help_text="Higher = shown more prominently in UI",
    )
    is_visible_to_others = models.BooleanField(
        default=True,
        help_text="Can other characters see this condition?",
    )

    # === Dynamic Thumbnail (#2196) ===
    thumbnail = models.ForeignKey(
        "evennia_extensions.Media",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="condition_template_thumbnails",
        help_text="Thumbnail shown when a character has this condition (overrides persona default)",
    )

    # === Property Grants ===
    properties = models.ManyToManyField(
        "mechanics.Property",
        related_name="condition_templates",
        blank=True,
        help_text=(
            "Properties temporarily granted while this condition is active. "
            "E.g., Werewolf Battleform grants 'clawed', 'bestial', 'large'."
        ),
    )

    # === Reactive Triggers ===
    reactive_triggers = models.ManyToManyField(
        "flows.TriggerDefinition",
        blank=True,
        related_name="installing_templates",
        help_text=(
            "TriggerDefinitions installed as Trigger rows on the bearer when an "
            "instance of this template is applied. Cleanup is automatic via "
            "Trigger.source_condition CASCADE on ConditionInstance deletion."
        ),
    )

    # === Aftermath / Decay (Scope 6 §4.1) ===
    parent_condition = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="aftermath_children",
        help_text=(
            "Aftermath conditions point at their primary parent (e.g. soul_ache → soulfray). "
            "FK is authoritative even before the aftermath is wired into any stage."
        ),
    )
    passive_decay_per_day = models.PositiveIntegerField(default=0)
    passive_decay_max_severity = models.PositiveIntegerField(null=True, blank=True)
    passive_decay_blocked_in_engagement = models.BooleanField(default=True)

    # === Clash-Lock Marker (Task 1.5) ===
    is_clash_lock = models.BooleanField(
        default=False,
        help_text=(
            "Marks this condition as a clash-lock — a Suppress/Break Free clash forms around it."
        ),
    )
    clash_lock_strength = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "The LOCK-clash MAX threshold (lock strength); set on clash-lock conditions. "
            "The LOCK-Clash MAX threshold (e.g. 10 = PCs must reach 10 progress to fully "
            "secure / fully break the lock)."
        ),
    )

    # === Reactive-defense cost ===
    upkeep_anima_per_round = models.PositiveIntegerField(
        default=0,
        help_text="Anima drained from the bearer each round to sustain this "
        "condition; can't pay → it lapses. 0 = free to maintain.",
    )
    reactive_anima_cost = models.PositiveIntegerField(
        default=0,
        help_text="Anima spent each time this condition's reactive effect fires "
        "(a dodge/reflect/absorb); can't pay → the effect fizzles. 0 = free.",
    )

    # === Corruption (Scope 7) ===
    corruption_resonance = models.ForeignKey(
        "magic.Resonance",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="corruption_condition_templates",
        help_text=(
            "Non-null marks this template as a per-resonance Corruption "
            "ConditionTemplate. Drives is_protagonism_locked detection and "
            "decay-time field sync for the resonance's corruption_current."
        ),
    )

    objects = NaturalKeyManager()

    # Name → PK cache for get_by_name (below). Class-level so service hot
    # paths (round ticks, condition advancement) reuse the cached PK
    # across calls. Flushed between tests via core.testing's registered
    # cache hook so test rollback can't leave stale PKs (see
    # core.testing module docstring for the rationale).
    _name_pk_cache: dict[str, int] = {}

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        ordering = ["category", "name"]

    def __str__(self) -> str:
        return self.name

    @classmethod
    def get_by_name(cls, name: str) -> ConditionTemplate:
        """Return the template with this name, leveraging the identity map.

        Service hot paths repeatedly look up known-must-exist templates by name
        (Soulfray, Audere, Bleeding-Out, etc.). Plain ``objects.get(name=NAME)``
        issues a fresh query every call because the identity map is keyed by PK,
        not name. This method maintains a class-level name→PK index so the
        second-and-after calls hit SharedMemoryModel's identity map directly
        (zero queries) instead of re-querying by name.

        Cache invalidation: the project test runner flushes ``_name_pk_cache``
        and ``SharedMemoryModel``'s identity map between tests (see
        ``core.testing``). In production the cache is stable because rows
        aren't deleted out from under it.

        Raises ConditionTemplate.DoesNotExist if no row matches.
        """
        cached_pk = cls._name_pk_cache.get(name)
        if cached_pk is not None:
            try:
                return cls.objects.get(pk=cached_pk)
            except cls.DoesNotExist:
                # Cache poisoned (e.g. somebody deleted the row in production);
                # drop and refetch.
                cls._name_pk_cache.pop(name, None)
        obj = cls.objects.get(name=name)  # raises DoesNotExist
        cls._name_pk_cache[name] = obj.pk
        return obj

    @cached_property
    def cached_stages(self) -> list[ConditionStage]:
        """Fallback for Prefetch(..., to_attr='cached_stages').

        When prefetched, Django populates this directly. When accessed without
        prefetch, falls back to a fresh query.
        """
        return list(self.stages.all())

    @cached_property
    def reactive_handler(self) -> ConditionTemplateReactiveHandler:
        from world.conditions.handlers import ConditionTemplateReactiveHandler  # noqa: PLC0415

        return ConditionTemplateReactiveHandler(self)


class ConditionStageManager(CachedAllMixin, NaturalKeyManager):
    """Manager for ConditionStage with natural key support, plus cached_all() (#1871)."""


class ConditionStage(NaturalKeyMixin, SharedMemoryModel):
    """
    A stage in a progressive condition.

    Example for Paralytic Poison:
      Stage 1: Numbness (minor penalties)
      Stage 2: Weakness (moderate penalties, slowed)
      Stage 3: Paralysis (movement blocked, severe penalties)
    """

    condition = models.ForeignKey(
        ConditionTemplate,
        on_delete=models.CASCADE,
        related_name="stages",
    )
    stage_order = models.PositiveIntegerField(
        help_text="Order in progression (1 = first stage)",
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    # Timing
    rounds_to_next = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Rounds until progression to next stage. Null = final stage.",
    )

    # Can a check prevent progression?
    resist_check_type = models.ForeignKey(
        "checks.CheckType",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Check type to resist progression",
    )
    resist_difficulty = models.PositiveIntegerField(
        default=10,
        help_text="Difficulty to resist progression",
    )

    # Stage-specific severity multiplier
    severity_multiplier = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("1.00"),
        help_text="Multiplier applied to condition effects at this stage",
    )

    # Severity-driven progression (alternative to time-based rounds_to_next)
    severity_threshold = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "When accumulated severity reaches this value, "
            "condition advances to this stage. Null = time-based only."
        ),
    )

    advancement_resist_failure_kind = models.CharField(
        max_length=24,
        choices=AdvancementResistFailureKind.choices,
        default=AdvancementResistFailureKind.ADVANCE_AT_THRESHOLD,
        help_text=(
            "Behavior when severity reaches this stage's threshold. "
            "ADVANCE_AT_THRESHOLD preserves existing behavior. "
            "HOLD_OVERFLOW gates advancement on a resist check using "
            "this stage's resist_check_type + resist_difficulty."
        ),
    )

    # Per-cast consequence pool (fires on every action while at this stage)
    consequence_pool = models.ForeignKey(
        _CONSEQUENCE_POOL_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="condition_stages",
        help_text="Consequence pool that fires per action while at this stage.",
    )

    # === Dynamic Thumbnail (#2196) ===
    thumbnail = models.ForeignKey(
        "evennia_extensions.Media",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="condition_stage_thumbnails",
        help_text=(
            "Thumbnail shown when a progressive condition is at this stage "
            "(overrides template thumbnail)"
        ),
    )

    # === Stage-level tags / on-entry hooks (Scope 6 §4.1) ===
    properties = models.ManyToManyField(
        "mechanics.Property",
        blank=True,
        related_name="condition_stages_carrying",
    )
    on_entry_conditions = models.ManyToManyField(
        _CONDITION_TEMPLATE_FK,
        through="conditions.ConditionStageOnEntry",
        related_name="applied_on_entry_of",
        blank=True,
    )

    objects = ConditionStageManager()

    class NaturalKeyConfig:
        fields = ["condition", "stage_order"]
        dependencies = [_CONDITION_TEMPLATE_FK]

    class Meta:
        unique_together = ["condition", "stage_order"]
        ordering = ["condition", "stage_order"]

    def __str__(self) -> str:
        return f"{self.condition.name} - {self.name}"


class ConditionStageOnEntry(SharedMemoryModel):
    """Through model: conditions applied when a target enters a stage (Scope 6 §4.1)."""

    stage = models.ForeignKey(
        ConditionStage,
        on_delete=models.CASCADE,
        related_name="on_entry_assocs",
    )
    condition = models.ForeignKey(
        ConditionTemplate,
        on_delete=models.PROTECT,
    )
    severity = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["stage", "condition"],
                name="unique_on_entry_condition_per_stage",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.stage} → {self.condition} (sev {self.severity})"


# =============================================================================
# Condition Effects - Abstract Base
# =============================================================================


class ConditionOrStageEffect(models.Model):
    """
    Abstract base class for effects that can apply to a condition or a stage.

    Uses mutually exclusive nullable FKs:
    - condition: set for "all stages" or non-progressive conditions
    - stage: set for stage-specific effects (condition derivable via stage.condition)

    Exactly one must be set, enforced by database CheckConstraint.
    Child classes must define their own UniqueConstraints since those involve
    model-specific fields.
    """

    condition = models.ForeignKey(
        "ConditionTemplate",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="%(class)s_set",
        help_text="Set for condition-level effects (all stages)",
    )
    stage = models.ForeignKey(
        "ConditionStage",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="%(class)s_set",
        help_text="Set for stage-specific effects",
    )
    scales_with_severity = models.BooleanField(
        default=False,
        help_text=(
            "When true, this effect's magnitude is multiplied by the condition "
            "instance's effective severity."
        ),
    )

    class Meta:
        abstract = True
        constraints = [
            models.CheckConstraint(
                check=(
                    Q(condition__isnull=False, stage__isnull=True)
                    | Q(condition__isnull=True, stage__isnull=False)
                ),
                name="%(app_label)s_%(class)s_exactly_one_target",
            ),
        ]

    def get_condition_template(self) -> ConditionTemplate:
        """Get the associated condition template."""
        if self.condition:
            return self.condition
        return self.stage.condition


# =============================================================================
# Condition Effects - Concrete Models
# =============================================================================


class ConditionCapabilityEffect(NaturalKeyMixin, ConditionOrStageEffect):
    """
    Defines how a condition affects a capability.

    Uses an additive integer model. Negative values reduce, positive enhance.
    A large negative effectively blocks the capability (value floors at 0).

    Examples:
      - Frozen: value=-100 (effectively blocks movement)
      - Slowed: value=-5 (reduces movement)
      - Empowered: value=+5 (enhances melee_attack)
    """

    capability = models.ForeignKey(CapabilityType, on_delete=models.CASCADE)
    value = models.IntegerField(
        default=0,
        help_text=(
            "Additive modifier. Negative reduces, positive enhances. "
            "A large negative effectively blocks the capability."
        ),
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["condition", "stage", "capability"]
        dependencies = [
            _CONDITION_TEMPLATE_FK,
            _CONDITION_STAGE_FK,
            "conditions.CapabilityType",
        ]

    class Meta(ConditionOrStageEffect.Meta):
        constraints = [
            *ConditionOrStageEffect.Meta.constraints,
            models.UniqueConstraint(
                fields=["condition", "capability"],
                condition=Q(condition__isnull=False),
                name="capability_effect_unique_condition",
            ),
            models.UniqueConstraint(
                fields=["stage", "capability"],
                condition=Q(stage__isnull=False),
                name="capability_effect_unique_stage",
            ),
        ]

    def __str__(self) -> str:
        if self.stage:
            return f"{self.stage.condition.name} ({self.stage.name}): {self.capability.name}"
        return f"{self.condition.name}: {self.capability.name}"


class ConditionModifierEffect(NaturalKeyMixin, ConditionOrStageEffect):
    """Defines how a condition sets a mechanics ModifierTarget value.

    Additive integer model, mirroring ConditionCapabilityEffect. Lets a condition
    feed the modifier system (e.g. a 'power' or 'power_multiplier' target) without
    materializing CharacterModifier rows — read at evaluation time. For
    'power_multiplier' the value is a percent-delta (35 = +35%); see _derive_power.
    """

    modifier_target = models.ForeignKey("mechanics.ModifierTarget", on_delete=models.CASCADE)
    value = models.IntegerField(
        default=0,
        help_text="Additive contribution to the modifier target (or percent-delta).",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["condition", "stage", "modifier_target"]
        dependencies = [
            _CONDITION_TEMPLATE_FK,
            _CONDITION_STAGE_FK,
            "mechanics.ModifierTarget",
        ]

    class Meta(ConditionOrStageEffect.Meta):
        constraints = [
            *ConditionOrStageEffect.Meta.constraints,
            models.UniqueConstraint(
                fields=["condition", "modifier_target"],
                condition=Q(condition__isnull=False),
                name="modifier_effect_unique_condition",
            ),
            models.UniqueConstraint(
                fields=["stage", "modifier_target"],
                condition=Q(stage__isnull=False),
                name="modifier_effect_unique_stage",
            ),
        ]

    def __str__(self) -> str:
        if self.stage:
            return f"{self.stage.condition.name} ({self.stage.name}): {self.modifier_target.name}"
        return f"{self.condition.name}: {self.modifier_target.name}"


class ConditionCheckModifier(NaturalKeyMixin, ConditionOrStageEffect):
    """
    Defines how a condition modifies checks.

    Examples:
      - Frightened gives -20 to combat_attack checks
      - Focused gives +10 to concentration checks
      - Wounded gives -5 to all physical checks
    """

    check_type = models.ForeignKey("checks.CheckType", on_delete=models.CASCADE)
    modifier_value = models.IntegerField(
        help_text="Flat modifier (positive = bonus, negative = penalty)",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["condition", "stage", "check_type"]
        dependencies = [
            _CONDITION_TEMPLATE_FK,
            _CONDITION_STAGE_FK,
            "checks.CheckType",
        ]

    class Meta(ConditionOrStageEffect.Meta):
        constraints = [
            *ConditionOrStageEffect.Meta.constraints,
            models.UniqueConstraint(
                fields=["condition", "check_type"],
                condition=Q(condition__isnull=False),
                name="check_modifier_unique_condition",
            ),
            models.UniqueConstraint(
                fields=["stage", "check_type"],
                condition=Q(stage__isnull=False),
                name="check_modifier_unique_stage",
            ),
        ]

    def __str__(self) -> str:
        sign = "+" if self.modifier_value >= 0 else ""
        if self.stage:
            return (
                f"{self.stage.condition.name} ({self.stage.name}): "
                f"{sign}{self.modifier_value} to {self.check_type.name}"
            )
        return f"{self.condition.name}: {sign}{self.modifier_value} to {self.check_type.name}"


class ConditionResistanceModifier(NaturalKeyMixin, ConditionOrStageEffect):
    """
    Defines how a condition modifies resistance to damage types.

    Examples:
      - Wet gives +50 resistance to fire
      - Wet gives -50 resistance to lightning
      - Brittle gives -100 resistance to force
      - Warded gives +30 resistance to all magic (damage_type=null)
    """

    damage_type = models.ForeignKey(
        DamageType,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="Specific damage type, or null for ALL damage types",
    )
    modifier_value = models.IntegerField(
        help_text="Modifier to resistance (positive = more resistant)",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["condition", "stage", "damage_type"]
        dependencies = [
            _CONDITION_TEMPLATE_FK,
            _CONDITION_STAGE_FK,
            "conditions.DamageType",
        ]

    class Meta(ConditionOrStageEffect.Meta):
        constraints = [
            *ConditionOrStageEffect.Meta.constraints,
            models.UniqueConstraint(
                fields=["condition", "damage_type"],
                condition=Q(condition__isnull=False),
                name="resistance_modifier_unique_condition",
            ),
            models.UniqueConstraint(
                fields=["stage", "damage_type"],
                condition=Q(stage__isnull=False),
                name="resistance_modifier_unique_stage",
            ),
        ]

    def __str__(self) -> str:
        sign = "+" if self.modifier_value >= 0 else ""
        dtype = self.damage_type.name if self.damage_type else "ALL"
        if self.stage:
            return (
                f"{self.stage.condition.name} ({self.stage.name}): "
                f"{sign}{self.modifier_value} resistance to {dtype}"
            )
        return f"{self.condition.name}: {sign}{self.modifier_value} resistance to {dtype}"


class ConditionDamageOverTime(NaturalKeyMixin, ConditionOrStageEffect):
    """
    Defines periodic damage for a condition.

    Examples:
      - Burning deals 5 fire damage per round
      - Bleeding deals 3 physical damage per round, severity-scaled
      - Poison deals 2 poison damage per round, increasing each stage
    """

    # DoT effects scale with severity by default (a more severe affliction deals
    # more damage); override the base's opt-in default=False to preserve behavior.
    scales_with_severity = models.BooleanField(
        default=True,
        help_text=(
            "When true, this effect's magnitude is multiplied by the condition "
            "instance's effective severity."
        ),
    )

    damage_type = models.ForeignKey(DamageType, on_delete=models.CASCADE)
    base_damage = models.PositiveIntegerField(help_text="Base damage per tick")
    scales_with_stacks = models.BooleanField(
        default=True,
        help_text="Multiply damage by stack count?",
    )
    tick_timing = models.CharField(
        max_length=20,
        choices=DamageTickTiming.choices,
        default=DamageTickTiming.END_OF_ROUND,
        help_text=(
            "When this DoT ticks. END_OF_ROUND is the convention (poison, sunlight) and the "
            "safe default. START_OF_ROUND means damage that lands BEFORE any action resolves "
            "this round, so it is intentionally un-shieldable by Succor/Interpose in combat "
            "AND currently inert in non-combat scene rounds (no scene-round START tick "
            "exists) — choose it deliberately. See docs/systems/conditions.md."
        ),
    )
    is_long_term = models.BooleanField(
        default=False,
        help_text=(
            "Long-term/chronic DoT: skipped by the per-round acute tick and instead "
            "advanced by the daily batch_chronic_effect_tick with a non-lethal clamp."
        ),
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["condition", "stage", "damage_type"]
        dependencies = [
            _CONDITION_TEMPLATE_FK,
            _CONDITION_STAGE_FK,
            "conditions.DamageType",
        ]

    class Meta(ConditionOrStageEffect.Meta):
        constraints = [
            *ConditionOrStageEffect.Meta.constraints,
            models.UniqueConstraint(
                fields=["condition", "damage_type"],
                condition=Q(condition__isnull=False),
                name="damage_over_time_unique_condition",
            ),
            models.UniqueConstraint(
                fields=["stage", "damage_type"],
                condition=Q(stage__isnull=False),
                name="damage_over_time_unique_stage",
            ),
        ]

    def __str__(self) -> str:
        if self.stage:
            return (
                f"{self.stage.condition.name} ({self.stage.name}): "
                f"{self.base_damage} {self.damage_type.name} per tick"
            )
        return f"{self.condition.name}: {self.base_damage} {self.damage_type.name} per tick"


# =============================================================================
# Condition Interactions
# =============================================================================


class ConditionDamageInteraction(NaturalKeyMixin, SharedMemoryModel):
    """
    Special interactions when a conditioned target takes specific damage.

    Examples:
      - Frozen + Force damage = +50% damage, removes Frozen
      - Burning + Cold damage = removes Burning
      - Wet + Fire damage = -30% damage (in addition to resistance)
    """

    condition = models.ForeignKey(
        ConditionTemplate,
        on_delete=models.CASCADE,
        related_name="damage_interactions",
    )
    damage_type = models.ForeignKey(
        DamageType,
        on_delete=models.CASCADE,
    )

    # Damage modification (in addition to resistance modifiers)
    damage_modifier_percent = models.IntegerField(
        default=0,
        help_text="Additional percentage modifier to damage",
    )

    # Does this remove the condition?
    removes_condition = models.BooleanField(
        default=False,
        help_text="Does taking this damage remove the condition?",
    )

    # Does this apply a different condition?
    applies_condition = models.ForeignKey(
        ConditionTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="applied_by_damage_interaction",
        help_text="Condition to apply as a result of this interaction",
    )
    applied_condition_severity = models.PositiveIntegerField(
        default=1,
        help_text="Severity of the applied condition",
    )
    narration_snippet = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Flavor text appended to combat narration when this interaction "
        "consumes or transforms a condition. Leave blank for a composed fallback.",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["condition", "damage_type"]
        dependencies = [
            _CONDITION_TEMPLATE_FK,
            "conditions.DamageType",
        ]

    class Meta:
        unique_together = ["condition", "damage_type"]

    def __str__(self) -> str:
        result = f"{self.condition.name} + {self.damage_type.name}"
        if self.removes_condition:
            result += " -> removes"
        if self.damage_modifier_percent:
            sign = "+" if self.damage_modifier_percent > 0 else ""
            result += f" ({sign}{self.damage_modifier_percent}% damage)"
        return result


class ConditionConditionInteraction(NaturalKeyMixin, SharedMemoryModel):
    """
    How conditions interact when both present or when one is applied.

    Examples:
      - Burning + Wet applied = Burning removed
      - Frozen prevents Burning from being applied
      - Poisoned + Antidote applied = Poisoned removed
      - Empowered + Weakened = both removed (cancel out)
    """

    condition = models.ForeignKey(
        ConditionTemplate,
        on_delete=models.CASCADE,
        related_name="interactions_as_primary",
    )
    other_condition = models.ForeignKey(
        ConditionTemplate,
        on_delete=models.CASCADE,
        related_name="interactions_as_secondary",
    )

    trigger = models.CharField(
        max_length=20,
        choices=ConditionInteractionTrigger.choices,
    )

    outcome = models.CharField(
        max_length=20,
        choices=ConditionInteractionOutcome.choices,
    )

    # For transform/merge outcomes
    result_condition = models.ForeignKey(
        ConditionTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_by_interaction",
        help_text="Resulting condition for transform/merge outcomes",
    )

    # Priority for conflicting interactions
    priority = models.PositiveIntegerField(
        default=0,
        help_text="Higher priority interactions resolve first",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["condition", "other_condition", "trigger"]
        dependencies = [_CONDITION_TEMPLATE_FK]

    class Meta:
        unique_together = ["condition", "other_condition", "trigger"]

    def __str__(self) -> str:
        return (
            f"{self.condition.name} + {self.other_condition.name} "
            f"({self.get_trigger_display()}) -> {self.get_outcome_display()}"
        )


# =============================================================================
# Condition Instances (Runtime State)
# =============================================================================


class ConditionInstance(SharedMemoryModel):
    """
    An active condition on a character, object, or room.

    All targets in Evennia are ObjectDB, so we use a single model.
    """

    target = models.ForeignKey(
        "objects.ObjectDB",
        on_delete=models.CASCADE,
        related_name="condition_instances",
    )
    condition = models.ForeignKey(
        ConditionTemplate,
        on_delete=models.CASCADE,
    )

    # === Current State ===
    current_stage = models.ForeignKey(
        ConditionStage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Current stage for progressive conditions",
    )
    stacks = models.PositiveIntegerField(default=1)
    severity = models.PositiveIntegerField(
        default=1,
        help_text="Intensity/potency affecting modifier scaling",
    )
    absorb_remaining = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Force-field buffer: damage points this instance can still "
        "absorb. Decremented by the absorb_pool handler; expires at 0. Null = not "
        "an absorb condition.",
    )

    # === Timing ===
    applied_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Absolute expiration time, if applicable",
    )
    rounds_remaining = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Rounds until expiration, if duration is rounds",
    )
    last_resist_attempt_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "When the bearer last manually attempted to shake this condition off "
            "(e.g. the wake check, #2287). Rate-limits out-of-combat attempts to "
            "one per round-equivalent (SECONDS_PER_ROUND)."
        ),
    )
    stage_rounds_remaining = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Rounds until progression to next stage",
    )

    # === Source Tracking ===
    source_character = models.ForeignKey(
        "objects.ObjectDB",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conditions_caused",
        help_text="Character who applied this condition",
    )
    source_technique = models.ForeignKey(
        "magic.Technique",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conditions_caused",
        help_text="Technique used to apply this condition",
    )
    source_vow = models.ForeignKey(
        "covenants.CovenantRole",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text=(
            "The applier's engaged-vow anchor at apply time (#2643) — the first of "
            "``character.covenant_roles.currently_engaged_roles()``, resolved to its "
            "anchor (``parent_role`` or itself, never a resolved sub-role). Null when "
            "the applier had no engaged role. Drives vow-keyed diminishing returns on "
            "the bounded team-damage-percent lane's read "
            "(``world.magic.services.techniques._team_lane_delta``): contributions "
            "sharing one vow diminish; distinct vows stack fully."
        ),
    )
    source_description = models.CharField(
        max_length=200,
        blank=True,
        help_text="Freeform description of source (e.g., 'poisoned wine')",
    )

    # === State Flags ===
    is_suppressed = models.BooleanField(
        default=False,
        help_text="Temporarily suppressed (effects don't apply)",
    )
    suppressed_until = models.DateTimeField(
        null=True,
        blank=True,
    )

    detected_by = models.ManyToManyField(
        "character_sheets.CharacterSheet",
        related_name="detected_concealments",
        blank=True,
        help_text=(
            "Characters who have pierced this specific concealing instance via a "
            "detection check. Per-observer: one character detecting it does not "
            "reveal it to anyone else. Only meaningful when the condition's category "
            "has conceals_from_perception=True."
        ),
    )

    # === Resolution (Scope 6 §4.1) ===
    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set when severity decays to 0. Used to filter out completed instances.",
    )

    # === Abandonment (#1479) ===
    abandoned_since_round = models.IntegerField(
        null=True,
        blank=True,
        help_text=(
            "Scene round_number at which this acute-peril condition was marked abandoned: "
            "the bearer is downed (present, cannot act) but no hostile party drove the round "
            "and a potential rescuer was present, so the peril HELD instead of advancing "
            "(#1479). Cleared (None) when a hostile party drives the round again."
        ),
    )

    # === Cast-time position targeting (#2019) ===
    cast_destination = models.ForeignKey(
        "areas.Position",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cast_destination_instances",
        help_text=(
            "For position-targeting conditions (Phase Jump, Force Grip): the "
            "destination Position chosen at cast time. Null for non-position "
            "conditions. Set by the cast pipeline; read by the effect handler "
            "via payload.instance.cast_destination."
        ),
    )
    cast_position_a = models.ForeignKey(
        "areas.Position",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cast_position_a_instances",
        help_text=(
            "For obstacle conditions (Barricade): the first Position of the "
            "edge to seal, chosen at cast time. Null for non-position conditions."
        ),
    )
    cast_position_b = models.ForeignKey(
        "areas.Position",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cast_position_b_instances",
        help_text=(
            "For obstacle conditions (Barricade): the second Position of the "
            "edge to seal, chosen at cast time. Null for non-position conditions."
        ),
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["target", "condition"],
                name="unique_condition_per_target",
            ),
        ]
        indexes = [
            models.Index(fields=["expires_at"]),
            models.Index(fields=["resolved_at"]),
        ]

    def __str__(self) -> str:
        stage_str = f" ({self.current_stage.name})" if self.current_stage else ""
        stack_str = f" x{self.stacks}" if self.stacks > 1 else ""
        return f"{self.condition.name}{stage_str}{stack_str} on {self.target}"

    @property
    def is_expired(self) -> bool:
        """Check if this condition has expired by rounds."""
        if self.rounds_remaining is not None:
            return self.rounds_remaining <= 0
        return False

    @property
    def effective_severity(self) -> int:
        """Get severity adjusted by current stage multiplier."""
        if self.current_stage:
            return int(self.severity * self.current_stage.severity_multiplier)
        return self.severity


# =============================================================================
# Treatments (Scope 6 §4.2)
# =============================================================================


class TreatmentTemplate(SharedMemoryModel):
    """
    Authorable recipe for attempting to treat a condition or pending alteration.

    Treatments come in three flavors (see ``target_kind``):
      - PRIMARY: reduce a primary condition's severity
      - AFTERMATH: reduce an aftermath child condition's severity
      - PENDING_ALTERATION: reduce a Mage Scar's pending alteration tier

    ``clean()`` enforces the narrative rule that any treatment with a resonance
    cost also requires a supporting bond thread (you can't spend bond resonance
    without a bond).
    """

    key = models.SlugField(unique=True, max_length=64)
    name = models.CharField(max_length=128)
    description = models.TextField(blank=True)

    target_condition = models.ForeignKey(
        _CONDITION_TEMPLATE_FK,
        on_delete=models.PROTECT,
        related_name="treatments",
    )
    target_kind = models.CharField(
        max_length=32,
        choices=TreatmentTargetKind.choices,
    )

    check_type = models.ForeignKey("checks.CheckType", on_delete=models.PROTECT)
    target_difficulty = models.PositiveIntegerField(default=0)
    requires_bond = models.BooleanField(default=False)

    resonance_cost = models.PositiveIntegerField(default=0)
    anima_cost = models.PositiveIntegerField(default=0)

    once_per_scene_per_helper = models.BooleanField(default=True)
    scene_required = models.BooleanField(default=True)

    backlash_severity_on_failure = models.PositiveIntegerField(default=0)
    backlash_target_condition = models.ForeignKey(
        _CONDITION_TEMPLATE_FK,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="treatment_backlash_source",
        help_text="When null, perform_treatment falls back to target_condition.",
    )

    reduction_on_crit = models.PositiveIntegerField(default=0)
    reduction_on_success = models.PositiveIntegerField(default=0)
    reduction_on_partial = models.PositiveIntegerField(default=0)
    reduction_on_failure = models.PositiveIntegerField(default=0)

    # === Bounded HP mend (#2644 — the attrition invariant) ===
    # Default 0 on all three: an existing severity-decay-only treatment is
    # unaffected (mend_on_* stay 0, mend_wound() never gets called for it).
    mend_on_crit = models.PositiveSmallIntegerField(
        default=0,
        help_text="HP mended on a critical success, routed through mend_wound() (0 = no mend).",
    )
    mend_on_success = models.PositiveSmallIntegerField(
        default=0,
        help_text="HP mended on a success, routed through mend_wound() (0 = no mend).",
    )
    mend_on_partial = models.PositiveSmallIntegerField(
        default=0,
        help_text="HP mended on a partial success, routed through mend_wound() (0 = no mend).",
    )
    once_per_wound_per_helper = models.BooleanField(
        default=False,
        help_text=(
            "When true, the duplicate-attempt gate keys on (helper, wound instance) "
            "instead of (helper, scene) — each healer gets exactly one tending per "
            "wound, ever, scene-independent (#2644). Mend-bearing treatments should "
            "set this True; leave once_per_scene_per_helper governing everything else."
        ),
    )

    def clean(self) -> None:
        super().clean()
        if self.resonance_cost > 0 and not self.requires_bond:
            from django.core.exceptions import ValidationError  # noqa: PLC0415

            raise ValidationError(
                {"resonance_cost": "resonance_cost > 0 requires requires_bond=True."},
            )

    def __str__(self) -> str:
        return self.name


class TreatmentAttempt(SharedMemoryModel):
    """
    Historical record of one helper attempting one treatment on one target in one scene.

    The partial UniqueConstraint enforces one attempt per
    (helper, target, scene, treatment) for treatments authored with
    ``once_per_scene_per_helper=True`` (denormalized at insert time onto
    ``once_per_scene_guard``). Treatments authored with
    ``once_per_scene_per_helper=False`` permit repeats. Postgres partial
    index — project is PG-only per CLAUDE.md.
    """

    helper = models.ForeignKey(
        "objects.ObjectDB",
        on_delete=models.PROTECT,
        related_name="treatment_attempts_as_helper",
    )
    target = models.ForeignKey(
        "objects.ObjectDB",
        on_delete=models.PROTECT,
        related_name="treatment_attempts_as_target",
    )
    scene = models.ForeignKey(
        "scenes.Scene",
        on_delete=models.PROTECT,
        related_name="treatment_attempts",
    )
    treatment = models.ForeignKey(
        "conditions.TreatmentTemplate",
        on_delete=models.PROTECT,
        related_name="attempts",
    )

    thread_used = models.ForeignKey(
        "magic.Thread",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="treatment_attempts",
    )

    target_condition_instance = models.ForeignKey(
        "conditions.ConditionInstance",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="treatment_attempts_targeting_instance",
    )
    target_pending_alteration = models.ForeignKey(
        "magic.PendingAlteration",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="treatment_attempts_targeting_alteration",
    )

    # CheckOutcome lookup row — FK to the catalog row, not a choices string.
    outcome = models.ForeignKey(
        "traits.CheckOutcome",
        on_delete=models.PROTECT,
        related_name="treatment_attempts",
    )
    severity_reduced = models.IntegerField(default=0)
    tiers_reduced = models.IntegerField(default=0)
    helper_backlash_applied = models.IntegerField(default=0)
    resonance_spent = models.IntegerField(default=0)
    anima_spent = models.IntegerField(default=0)
    health_mended = models.IntegerField(
        default=0,
        help_text=(
            "HP actually mended by this attempt, as returned by "
            "world.vitals.services.mend_wound() (#2644) — may be less than the "
            "treatment's mend_on_* value when the fraction cap or max_health "
            "clamp bit. 0 for non-wound treatments and for every failure."
        ),
    )

    created_at = models.DateTimeField(
        help_text="Stamped at save with get_ic_now() fallback in the service.",
    )

    once_per_scene_guard = models.BooleanField(
        default=False,
        editable=False,
        help_text=(
            "Denormalized from treatment.once_per_scene_per_helper at insert time. "
            "True = the partial unique constraint enforces one attempt per "
            "(helper, target, scene, treatment). False = repeats permitted for "
            "treatments authored with once_per_scene_per_helper=False. See spec "
            "2026-05-09 §4.10."
        ),
    )
    once_per_wound_guard = models.BooleanField(
        default=False,
        editable=False,
        help_text=(
            "Denormalized from treatment.once_per_wound_per_helper at insert time "
            "(#2644) — mirrors once_per_scene_guard's pattern. True = the partial "
            "unique constraint enforces one attempt per (helper, target_condition_"
            "instance), scene-independent. False = the once_per_scene_guard (or no) "
            "gate governs instead."
        ),
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["helper", "target", "scene", "treatment"],
                condition=models.Q(once_per_scene_guard=True),
                name="unique_treatment_attempt_per_helper_scene",
            ),
            models.UniqueConstraint(
                fields=["helper", "target_condition_instance"],
                condition=models.Q(once_per_wound_guard=True),
                name="unique_treatment_attempt_per_helper_wound",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.treatment} on {self.target} by {self.helper}"


# =============================================================================
# Damage Scaling Lookup
# =============================================================================


class DamageSuccessLevelMultiplier(NaturalKeyMixin, SharedMemoryModel):
    """Tunable lookup: success_level → damage multiplier.

    Resolver picks the highest-threshold row whose `min_success_level` is
    ≤ the actual SL. SL below the lowest threshold yields zero damage.
    Defaults seeded by the planned startup-page mechanism (or
    DamageSuccessLevelMultiplierFactory in tests).
    """

    min_success_level = models.IntegerField(unique=True)
    multiplier = models.DecimalField(max_digits=4, decimal_places=2)
    label = models.CharField(max_length=64, blank=True)

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["min_success_level"]

    class Meta:
        ordering = ["-min_success_level"]

    def __str__(self) -> str:
        suffix = f" — {self.label}" if self.label else ""
        return f"SL ≥ {self.min_success_level}: ×{self.multiplier}{suffix}"


class PenetrationOutcomeFactor(NaturalKeyMixin, SharedMemoryModel):
    """Authored success-level → power factor for the penetration contest (#639).

    A working that targets a warded opponent rolls a penetration check against
    the target's ``CombatOpponent.barrier_strength``. The check's success level
    selects a factor that SCALES the (already-derived) power before it enters
    the unchanged damage/condition path. A ``factor`` of ``0.00`` means the
    working "bounced off the ward" (zero effective power). Mirrors
    :class:`DamageSuccessLevelMultiplier`: the resolver picks the highest
    authored row whose ``min_success_level`` is ≤ the actual SL.
    """

    min_success_level = models.IntegerField(unique=True)
    factor = models.DecimalField(max_digits=4, decimal_places=2)
    label = models.CharField(max_length=64, blank=True)

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["min_success_level"]

    class Meta:
        ordering = ["-min_success_level"]

    def __str__(self) -> str:
        suffix = f" — {self.label}" if self.label else ""
        return f"SL ≥ {self.min_success_level}: ×{self.factor}{suffix}"
