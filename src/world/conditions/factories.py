"""
Factories for conditions app tests.
"""

from decimal import Decimal

import factory
from factory.django import DjangoModelFactory

from flows.factories import (
    FlowDefinitionFactory,
    TriggerDefinitionFactory,
    TriggerFactory,
)
from world.conditions.constants import (
    ConditionInteractionOutcome,
    ConditionInteractionTrigger,
    DamageTickTiming,
    DurationType,
    TreatmentTargetKind,
)
from world.conditions.models import (
    CapabilityType,
    ConditionCapabilityEffect,
    ConditionCategory,
    ConditionCheckModifier,
    ConditionConditionInteraction,
    ConditionDamageInteraction,
    ConditionDamageOverTime,
    ConditionInstance,
    ConditionResistanceModifier,
    ConditionStage,
    ConditionTemplate,
    DamageSuccessLevelMultiplier,
    DamageType,
    TreatmentTemplate,
)


class ConditionCategoryFactory(DjangoModelFactory):
    """Factory for ConditionCategory."""

    class Meta:
        model = ConditionCategory
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Category {n}")
    description = "Test category"
    is_negative = True
    display_order = factory.Sequence(lambda n: n)


class CapabilityTypeFactory(DjangoModelFactory):
    """Factory for CapabilityType."""

    class Meta:
        model = CapabilityType
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Capability {n}")
    description = "Test capability"


class DamageTypeFactory(DjangoModelFactory):
    """Factory for DamageType."""

    class Meta:
        model = DamageType
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Damage {n}")
    description = "Test damage type"
    color_hex = "#FF0000"


class ConditionTemplateFactory(DjangoModelFactory):
    """Factory for ConditionTemplate."""

    class Meta:
        model = ConditionTemplate
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Condition {n}")
    category = factory.SubFactory(ConditionCategoryFactory)
    description = "Test condition"
    default_duration_type = DurationType.ROUNDS
    default_duration_value = 3
    is_stackable = False
    max_stacks = 1
    has_progression = False
    can_be_dispelled = True


class ConditionStageFactory(DjangoModelFactory):
    """Factory for ConditionStage."""

    class Meta:
        model = ConditionStage

    condition = factory.SubFactory(ConditionTemplateFactory, has_progression=True)
    stage_order = factory.Sequence(lambda n: (n % 5) + 1)  # cycle 1..5 to prevent overflow
    name = factory.Sequence(lambda n: f"Stage {n + 1}")
    description = "Test stage"
    rounds_to_next = 2
    severity_multiplier = factory.LazyAttribute(
        lambda o: round(1.0 + ((o.stage_order - 1) * 0.5), 2)
    )
    severity_threshold = None
    consequence_pool = None


class ConditionCapabilityEffectFactory(DjangoModelFactory):
    """Factory for ConditionCapabilityEffect."""

    class Meta:
        model = ConditionCapabilityEffect

    condition = factory.SubFactory(ConditionTemplateFactory)
    stage = None
    capability = factory.SubFactory(CapabilityTypeFactory)
    value = -25


class ConditionCheckModifierFactory(DjangoModelFactory):
    """Factory for ConditionCheckModifier."""

    class Meta:
        model = ConditionCheckModifier

    condition = factory.SubFactory(ConditionTemplateFactory)
    stage = None
    check_type = factory.SubFactory("world.checks.factories.CheckTypeFactory")
    modifier_value = -10
    scales_with_severity = False


class ConditionResistanceModifierFactory(DjangoModelFactory):
    """Factory for ConditionResistanceModifier."""

    class Meta:
        model = ConditionResistanceModifier

    condition = factory.SubFactory(ConditionTemplateFactory)
    stage = None
    damage_type = factory.SubFactory(DamageTypeFactory)
    modifier_value = 25


class ConditionDamageOverTimeFactory(DjangoModelFactory):
    """Factory for ConditionDamageOverTime."""

    class Meta:
        model = ConditionDamageOverTime

    condition = factory.SubFactory(ConditionTemplateFactory)
    stage = None
    damage_type = factory.SubFactory(DamageTypeFactory)
    base_damage = 5
    scales_with_severity = True
    scales_with_stacks = True
    tick_timing = DamageTickTiming.START_OF_ROUND


class ConditionDamageInteractionFactory(DjangoModelFactory):
    """Factory for ConditionDamageInteraction."""

    class Meta:
        model = ConditionDamageInteraction

    condition = factory.SubFactory(ConditionTemplateFactory)
    damage_type = factory.SubFactory(DamageTypeFactory)
    damage_modifier_percent = 50
    removes_condition = False
    applies_condition = None
    applied_condition_severity = 1


class ConditionConditionInteractionFactory(DjangoModelFactory):
    """Factory for ConditionConditionInteraction."""

    class Meta:
        model = ConditionConditionInteraction

    condition = factory.SubFactory(ConditionTemplateFactory)
    other_condition = factory.SubFactory(ConditionTemplateFactory)
    trigger = ConditionInteractionTrigger.ON_OTHER_APPLIED
    outcome = ConditionInteractionOutcome.REMOVE_SELF
    result_condition = None
    priority = 0


class ConditionInstanceFactory(DjangoModelFactory):
    """Factory for ConditionInstance."""

    class Meta:
        model = ConditionInstance

    target = factory.LazyFunction(
        lambda: __import__("evennia.objects.models", fromlist=["ObjectDB"]).ObjectDB.objects.create(
            db_key="TestTarget"
        )
    )
    condition = factory.SubFactory(ConditionTemplateFactory)
    current_stage = None
    stacks = 1
    severity = 1
    rounds_remaining = 3
    stage_rounds_remaining = None
    source_character = None
    source_technique = None
    source_description = ""
    is_suppressed = False


class TreatmentTemplateFactory(DjangoModelFactory):
    """Factory for TreatmentTemplate."""

    class Meta:
        model = TreatmentTemplate

    key = factory.Sequence(lambda n: f"treatment-{n}")
    name = factory.Sequence(lambda n: f"Treatment {n}")
    description = "Test treatment"
    target_condition = factory.SubFactory(ConditionTemplateFactory)
    target_kind = TreatmentTargetKind.AFTERMATH
    check_type = factory.SubFactory("world.checks.factories.CheckTypeFactory")
    target_difficulty = 0
    requires_bond = False
    resonance_cost = 0
    anima_cost = 0
    once_per_scene_per_helper = True
    scene_required = True
    backlash_severity_on_failure = 0
    backlash_target_condition = None
    reduction_on_crit = 5
    reduction_on_success = 3
    reduction_on_partial = 1
    reduction_on_failure = 0


class _ReactiveConditionFactory:
    """Helper that composes Event + TriggerDefinition + ConditionInstance + Trigger.

    Not a DjangoModelFactory — this is a callable composition wrapper.
    Callers invoke ``ReactiveConditionFactory(event_name=...)`` mimicking the
    DjangoModelFactory API.

    Use ``target=...`` to attach the reactive condition to an existing ObjectDB
    (Character, room, item). If omitted, the underlying ConditionInstanceFactory
    creates a throwaway ObjectDB.
    """

    @classmethod
    def create(
        cls,
        *,
        event_name: str,
        filter_condition: dict | None = None,
        flow_definition=None,
        target=None,
        stage=None,
    ):
        flow_def = flow_definition or FlowDefinitionFactory()
        trigger_def = TriggerDefinitionFactory(
            event_name=event_name,
            flow_definition=flow_def,
        )
        condition_kwargs = {}
        if target is not None:
            condition_kwargs["target"] = target
        condition = ConditionInstanceFactory(**condition_kwargs)
        return TriggerFactory(
            trigger_definition=trigger_def,
            obj=condition.target,
            source_condition=condition,
            source_stage=stage,
            additional_filter_condition=filter_condition,
        )

    def __call__(self, **kwargs):
        return self.create(**kwargs)


ReactiveConditionFactory = _ReactiveConditionFactory()


# =============================================================================
# Scope 6 §8.3 — Aftermath condition factories
# =============================================================================


def _get_soulfray_template() -> ConditionTemplate:
    """Return the Soulfray ConditionTemplate, creating it if absent.

    Aftermath factories use this as a LazyFunction so they can be created in
    isolation (without calling SoulfrayContentFactory first). Callers that
    need the full seeded content (stages + properties) should use
    ``SoulfrayContentFactory()`` from ``world.magic.factories`` instead.
    """
    from world.magic.audere import SOULFRAY_CONDITION_NAME

    template, _ = ConditionTemplate.objects.get_or_create(
        name=SOULFRAY_CONDITION_NAME,
        defaults={
            "description": "Soulfray condition (auto-created by aftermath factory).",
            "has_progression": True,
            "passive_decay_per_day": 1,
            "passive_decay_blocked_in_engagement": True,
        },
    )
    return template


def _default_treatment_check_type():
    """Return a throwaway CheckType for treatment factories.

    Seed-tuning PRs can replace the check type explicitly; this gives a
    usable default so tests don't require manual wiring.
    """
    from world.checks.factories import CheckTypeFactory

    return CheckTypeFactory()


class SoulAcheTemplateFactory(ConditionTemplateFactory):
    """Seed factory for the 'soul_ache' aftermath condition (§8.3)."""

    name = "soul_ache"
    description = "A dull, persistent ache in the soul."
    parent_condition = factory.LazyFunction(_get_soulfray_template)


class ArcaneTremorTemplateFactory(ConditionTemplateFactory):
    """Seed factory for the 'arcane_tremor' aftermath condition (§8.3)."""

    name = "arcane_tremor"
    description = "Uncontrolled tremors in the magical pathways."
    parent_condition = factory.LazyFunction(_get_soulfray_template)


class AuraBleedTemplateFactory(ConditionTemplateFactory):
    """Seed factory for the 'aura_bleed' aftermath condition (§8.3)."""

    name = "aura_bleed"
    description = "The aura bleeds raw power, leaving the mage dangerously exposed."
    parent_condition = factory.LazyFunction(_get_soulfray_template)


# =============================================================================
# Scope 6 §8.5 — Soulfray treatment template factories
# =============================================================================


class SoulfrayStabilizeAftermathTreatmentFactory(DjangoModelFactory):
    """Seed factory for 'soulfray_stabilize_aftermath' treatment (§8.5)."""

    class Meta:
        model = TreatmentTemplate
        django_get_or_create = ("key",)

    key = "soulfray_stabilize_aftermath"
    name = "Stabilize Soulfray Aftermath"
    description = "An ally attempts to stabilize a Soulfray aftermath condition."
    target_condition = factory.LazyFunction(_get_soulfray_template)
    target_kind = TreatmentTargetKind.AFTERMATH
    check_type = factory.LazyFunction(_default_treatment_check_type)
    requires_bond = True
    resonance_cost = 1
    anima_cost = 0
    once_per_scene_per_helper = True
    backlash_severity_on_failure = 1
    backlash_target_condition = factory.LazyFunction(_get_soulfray_template)
    reduction_on_crit = 3
    reduction_on_success = 2
    reduction_on_partial = 1
    reduction_on_failure = 0


class SoulfrayStabilizeMageScarTreatmentFactory(DjangoModelFactory):
    """Seed factory for 'soulfray_stabilize_mage_scar' treatment (§8.5)."""

    class Meta:
        model = TreatmentTemplate
        django_get_or_create = ("key",)

    key = "soulfray_stabilize_mage_scar"
    name = "Stabilize Pending Mage Scar"
    description = "An ally attempts to reduce the severity of a pending Mage Scar."
    target_condition = factory.LazyFunction(_get_soulfray_template)
    target_kind = TreatmentTargetKind.PENDING_ALTERATION
    check_type = factory.LazyFunction(_default_treatment_check_type)
    requires_bond = True
    resonance_cost = 2
    anima_cost = 0
    once_per_scene_per_helper = True
    backlash_severity_on_failure = 1
    backlash_target_condition = factory.LazyFunction(_get_soulfray_template)
    reduction_on_crit = 2
    reduction_on_success = 1
    reduction_on_partial = 1
    reduction_on_failure = 0


class DamageSuccessLevelMultiplierFactory(DjangoModelFactory):
    class Meta:
        model = DamageSuccessLevelMultiplier
        django_get_or_create = ("min_success_level",)

    min_success_level = 2
    multiplier = Decimal("1.00")
    label = "Full"
