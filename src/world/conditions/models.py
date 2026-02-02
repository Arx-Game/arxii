"""
Conditions System Models

Conditions are persistent states on targets (characters, objects, rooms) that
modify capabilities, checks, and resistances. They can progress through stages,
interact with damage types, and interact with other conditions.

Design doc: docs/plans/2026-01-25-conditions-models-design.md
"""

from decimal import Decimal

from django.db import models
from django.db.models import Q
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.conditions.constants import (
    CapabilityEffectType,
    ConditionInteractionOutcome,
    ConditionInteractionTrigger,
    DamageTickTiming,
    DurationType,
    StackBehavior,
)

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

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name_plural = "Condition Categories"

    def __str__(self) -> str:
        return self.name


class CapabilityType(NaturalKeyMixin, SharedMemoryModel):
    """
    Capabilities that can be restricted or enhanced by conditions.

    Examples: movement, speech, fine_manipulation, perception,
              magic_use, melee_attack, ranged_attack, concentration
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    def __str__(self) -> str:
        return self.name


class CheckType(NaturalKeyMixin, SharedMemoryModel):
    """
    Types of checks that can receive bonuses/penalties from conditions.

    Examples: stealth, perception, social, combat_attack, combat_defense,
              magic_control, concentration, athletics, acrobatics
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    objects = NaturalKeyManager()

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
    # Resonances are now ModifierType entries with category='resonance'
    resonance = models.OneToOneField(
        "mechanics.ModifierType",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="damage_type",
        help_text="Associated magical resonance (category='resonance'), if any",
    )

    # Display
    color_hex = models.CharField(
        max_length=7,
        blank=True,
        help_text="Hex color for UI display (e.g., #FF4400 for fire)",
    )
    icon = models.CharField(max_length=100, blank=True)

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
        CheckType,
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

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        ordering = ["category", "name"]

    def __str__(self) -> str:
        return self.name


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
        CheckType,
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

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["condition", "stage_order"]
        dependencies = ["conditions.ConditionTemplate"]

    class Meta:
        unique_together = ["condition", "stage_order"]
        ordering = ["condition", "stage_order"]

    def __str__(self) -> str:
        return f"{self.condition.name} - {self.name}"


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

    def get_condition_template(self) -> "ConditionTemplate":
        """Get the associated condition template."""
        if self.condition:
            return self.condition
        return self.stage.condition


# =============================================================================
# Condition Effects - Concrete Models
# =============================================================================


class ConditionCapabilityEffect(ConditionOrStageEffect):
    """
    Defines how a condition affects a capability.

    Examples:
      - Frozen blocks movement
      - Slowed reduces movement by 50%
      - Empowered enhances melee_attack
    """

    capability = models.ForeignKey(CapabilityType, on_delete=models.CASCADE)
    effect_type = models.CharField(max_length=20, choices=CapabilityEffectType.choices)
    modifier_percent = models.IntegerField(
        default=0,
        help_text="Percentage modifier for reduced/enhanced (e.g., -50 or +25)",
    )

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


class ConditionCheckModifier(ConditionOrStageEffect):
    """
    Defines how a condition modifies checks.

    Examples:
      - Frightened gives -20 to combat_attack checks
      - Focused gives +10 to concentration checks
      - Wounded gives -5 to all physical checks
    """

    check_type = models.ForeignKey(CheckType, on_delete=models.CASCADE)
    modifier_value = models.IntegerField(
        help_text="Flat modifier (positive = bonus, negative = penalty)",
    )
    scales_with_severity = models.BooleanField(
        default=False,
        help_text="If true, modifier is multiplied by condition severity",
    )

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


class ConditionResistanceModifier(ConditionOrStageEffect):
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


class ConditionDamageOverTime(ConditionOrStageEffect):
    """
    Defines periodic damage for a condition.

    Examples:
      - Burning deals 5 fire damage per round
      - Bleeding deals 3 physical damage per round, severity-scaled
      - Poison deals 2 poison damage per round, increasing each stage
    """

    damage_type = models.ForeignKey(DamageType, on_delete=models.CASCADE)
    base_damage = models.PositiveIntegerField(help_text="Base damage per tick")
    scales_with_severity = models.BooleanField(
        default=True,
        help_text="Multiply damage by condition severity?",
    )
    scales_with_stacks = models.BooleanField(
        default=True,
        help_text="Multiply damage by stack count?",
    )
    tick_timing = models.CharField(
        max_length=20,
        choices=DamageTickTiming.choices,
        default=DamageTickTiming.START_OF_ROUND,
    )

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


class ConditionDamageInteraction(models.Model):
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


class ConditionConditionInteraction(models.Model):
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


class ConditionInstance(models.Model):
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

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["target", "condition"],
                name="unique_condition_per_target",
            ),
        ]
        indexes = [
            models.Index(fields=["expires_at"]),
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
