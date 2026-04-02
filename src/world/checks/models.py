"""Check system models."""

from django.core.exceptions import ValidationError
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.checks.constants import EffectTarget, EffectType


class CheckCategory(NaturalKeyMixin, SharedMemoryModel):
    """Grouping for check types (Social, Combat, Exploration, Magic)."""

    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    display_order = models.PositiveIntegerField(default=0)

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name_plural = "Check categories"

    def __str__(self):
        return self.name


class CheckType(NaturalKeyMixin, SharedMemoryModel):
    """Staff-defined check type with trait and aspect composition."""

    name = models.CharField(max_length=100)
    category = models.ForeignKey(
        CheckCategory,
        on_delete=models.CASCADE,
        related_name="check_types",
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name", "category"]
        dependencies = ["checks.CheckCategory"]

    class Meta:
        ordering = ["category__display_order", "display_order", "name"]
        unique_together = ["name", "category"]

    def __str__(self):
        return self.name


class CheckTypeTrait(NaturalKeyMixin, SharedMemoryModel):
    """Weighted trait contribution to a check type."""

    check_type = models.ForeignKey(
        CheckType,
        on_delete=models.CASCADE,
        related_name="traits",
    )
    trait = models.ForeignKey(
        "traits.Trait",
        on_delete=models.CASCADE,
        related_name="check_type_traits",
    )
    weight = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=1.0,
        help_text="Multiplier for this trait's contribution (default 1.0)",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["check_type", "trait"]
        dependencies = ["checks.CheckType", "traits.Trait"]

    class Meta:
        unique_together = ["check_type", "trait"]

    def __str__(self):
        return f"{self.check_type.name}: {self.trait.name} ({self.weight}x)"


class CheckTypeAspect(NaturalKeyMixin, SharedMemoryModel):
    """Weighted aspect relevance for a check type."""

    check_type = models.ForeignKey(
        CheckType,
        on_delete=models.CASCADE,
        related_name="aspects",
    )
    aspect = models.ForeignKey(
        "classes.Aspect",
        on_delete=models.CASCADE,
        related_name="check_type_aspects",
    )
    weight = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=1.0,
        help_text="Relevance multiplier for this aspect (default 1.0)",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["check_type", "aspect"]
        dependencies = ["checks.CheckType", "classes.Aspect"]

    class Meta:
        unique_together = ["check_type", "aspect"]

    def __str__(self):
        return f"{self.check_type.name}: {self.aspect.name} ({self.weight}x)"


# ---------------------------------------------------------------------------
# Generic Consequence system
# ---------------------------------------------------------------------------


class Consequence(SharedMemoryModel):
    """
    A possible outcome tied to a CheckOutcome tier.

    Generic consequence used by any system that maps check results to weighted
    outcomes: challenges, combat, magic, social scenes, etc. Domain-specific
    systems reference Consequence via through models that add context
    (e.g., ChallengeTemplateConsequence adds resolution_type).
    """

    outcome_tier = models.ForeignKey(
        "traits.CheckOutcome",
        on_delete=models.CASCADE,
        related_name="consequences",
    )
    label = models.CharField(max_length=200)
    mechanical_description = models.TextField(blank=True)
    weight = models.PositiveIntegerField(default=1)
    character_loss = models.BooleanField(default=False)

    def __str__(self) -> str:
        return self.label


class ConsequenceEffect(SharedMemoryModel):
    """
    A structured mechanical effect applied when a consequence is selected.

    Each consequence can have zero or more effects, executed in order.
    The effect_type determines which fields are relevant; clean() validates
    that the correct fields are populated.
    """

    consequence = models.ForeignKey(
        Consequence,
        on_delete=models.CASCADE,
        related_name="effects",
    )
    effect_type = models.CharField(
        max_length=20,
        choices=EffectType.choices,
    )
    execution_order = models.PositiveIntegerField(default=0)
    target = models.CharField(
        max_length=20,
        choices=EffectTarget.choices,
        default=EffectTarget.SELF,
    )

    # Condition effects
    condition_template = models.ForeignKey(
        "conditions.ConditionTemplate",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="consequence_effects",
    )
    condition_severity = models.PositiveIntegerField(null=True, blank=True)

    # Property effects
    property = models.ForeignKey(
        "mechanics.Property",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="consequence_effects",
    )
    property_value = models.PositiveIntegerField(null=True, blank=True)

    # Damage effects (stubbed — needs HP/combat system)
    damage_amount = models.PositiveIntegerField(null=True, blank=True)
    damage_type = models.ForeignKey(
        "conditions.DamageType",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="consequence_effects",
    )

    # Flow effects
    flow_definition = models.ForeignKey(
        "flows.FlowDefinition",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="consequence_effects",
    )

    # Codex effects
    codex_entry = models.ForeignKey(
        "codex.CodexEntry",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="consequence_effects",
    )

    class Meta:
        ordering = ["execution_order"]

    def __str__(self) -> str:
        return f"{self.consequence.label}: {self.get_effect_type_display()}"

    # Maps effect_type -> list of (field_name, id_attr) that must be set.
    _REQUIRED_FIELDS: dict[str, list[tuple[str, str]]] = {
        EffectType.APPLY_CONDITION: [("condition_template", "condition_template_id")],
        EffectType.REMOVE_CONDITION: [("condition_template", "condition_template_id")],
        EffectType.ADD_PROPERTY: [("property", "property_id")],
        EffectType.REMOVE_PROPERTY: [("property", "property_id")],
        EffectType.DEAL_DAMAGE: [
            ("damage_amount", "damage_amount"),
            ("damage_type", "damage_type_id"),
        ],
        EffectType.LAUNCH_ATTACK: [("damage_type", "damage_type_id")],
        EffectType.LAUNCH_FLOW: [("flow_definition", "flow_definition_id")],
        EffectType.GRANT_CODEX: [("codex_entry", "codex_entry_id")],
        EffectType.MAGICAL_SCARS: [("condition_template", "condition_template_id")],
    }

    def clean(self) -> None:
        """Validate that the correct fields are populated for the effect type."""
        required = self._REQUIRED_FIELDS.get(self.effect_type, [])
        errors: dict[str, str] = {}
        for field_name, id_attr in required:
            if not getattr(self, id_attr, None):
                errors[field_name] = f"{field_name} is required for {self.effect_type}"
        if errors:
            raise ValidationError(errors)
