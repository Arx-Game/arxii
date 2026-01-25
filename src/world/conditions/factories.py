"""
Factories for conditions app tests.
"""

import factory
from factory.django import DjangoModelFactory

from world.conditions.constants import (
    CapabilityEffectType,
    ConditionInteractionOutcome,
    ConditionInteractionTrigger,
    DamageTickTiming,
    DurationType,
)
from world.conditions.models import (
    CapabilityType,
    CheckType,
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
    DamageType,
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


class CheckTypeFactory(DjangoModelFactory):
    """Factory for CheckType."""

    class Meta:
        model = CheckType
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Check {n}")
    description = "Test check type"


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
    stage_order = factory.Sequence(lambda n: n + 1)
    name = factory.Sequence(lambda n: f"Stage {n + 1}")
    description = "Test stage"
    rounds_to_next = 2
    severity_multiplier = factory.LazyAttribute(lambda o: 1.0 + (o.stage_order - 1) * 0.5)


class ConditionCapabilityEffectFactory(DjangoModelFactory):
    """Factory for ConditionCapabilityEffect."""

    class Meta:
        model = ConditionCapabilityEffect

    condition = factory.SubFactory(ConditionTemplateFactory)
    stage = None
    capability = factory.SubFactory(CapabilityTypeFactory)
    effect_type = CapabilityEffectType.REDUCED
    modifier_percent = -25


class ConditionCheckModifierFactory(DjangoModelFactory):
    """Factory for ConditionCheckModifier."""

    class Meta:
        model = ConditionCheckModifier

    condition = factory.SubFactory(ConditionTemplateFactory)
    stage = None
    check_type = factory.SubFactory(CheckTypeFactory)
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
    source_power = None
    source_description = ""
    is_suppressed = False
