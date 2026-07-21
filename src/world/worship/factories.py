"""FactoryBoy factories for worship models (#2355)."""

import factory

from world.skills.factories import SpecializationFactory
from world.worship.models import (
    DevotionStanding,
    WorshipDeclaration,
    WorshippedBeing,
    WorshipTradition,
)


class WorshipTraditionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = WorshipTradition

    name = factory.Sequence(lambda n: f"Tradition {n}")
    description = "PLACEHOLDER tradition lore."
    rites_specialization = factory.SubFactory(SpecializationFactory)


class WorshippedBeingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = WorshippedBeing

    name = factory.Sequence(lambda n: f"Being {n}")
    description = "PLACEHOLDER being lore."
    tradition = factory.SubFactory(WorshipTraditionFactory)
    is_active = True


class DevotionStandingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = DevotionStanding

    being = factory.SubFactory(WorshippedBeingFactory)
    favor = 0
    lifetime_favor = 0


class WorshipDeclarationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = WorshipDeclaration

    public_being = factory.SubFactory(WorshippedBeingFactory)


class MiracleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "worship.Miracle"

    name = factory.Sequence(lambda n: f"Miracle {n}")
    being = factory.SubFactory(WorshippedBeingFactory)
    resonance_pool_cost = 100
    intervention_trigger = "incapacitated"
    favor_threshold = 50
    narrative_text = "[PLACEHOLDER] A divine power manifests."
    is_active = True
    sort_order = 0


class DivineInterventionConfigFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "worship.DivineInterventionConfig"
        django_get_or_create = ("pk",)

    pk = 1
    favor_threshold = 50
    cooldown_hours = 24
    min_pool_for_intervention = 100


def wire_miracle_content() -> None:
    """Seed TriggerDefinition, FlowDefinition, config, ConditionTemplate, example miracles.

    Idempotent. Called from ``seed_worship_content()``.
    """
    from flows.consts import FlowActionChoices
    from flows.factories import FlowStepDefinitionFactory
    from flows.models import FlowDefinition, TriggerDefinition
    from world.conditions.factories import ConditionTemplateFactory
    from world.worship.constants import MiracleTrigger
    from world.worship.models import Miracle
    from world.worship.services import get_divine_intervention_config

    # 1. Flow + TriggerDefinition
    flow, _ = FlowDefinition.objects.get_or_create(name="divine_intervention_flow")
    if not flow.steps.exists():
        FlowStepDefinitionFactory(
            flow=flow,
            action=FlowActionChoices.CALL_SERVICE_FUNCTION,
            variable_name="world.worship.services.maybe_fire_divine_intervention",
            parameters={"payload": "{{payload}}"},
        )
    TriggerDefinition.objects.get_or_create(
        name="divine_intervention_on_incapacitated",
        defaults={
            "event_name": "character_incapacitated",
            "flow_definition": flow,
            "priority": 60,
        },
    )

    # 2. Config singleton
    get_divine_intervention_config()

    # 3. Cooldown ConditionTemplate
    ConditionTemplateFactory(name="Divine Intervention Cooldown")

    # 4. Example miracles for seeded beings (PLACEHOLDER)
    for being in WorshippedBeing.objects.filter(is_active=True):
        Miracle.objects.get_or_create(
            being=being,
            name=f"{being.name}'s Aegis",
            defaults={
                "resonance_pool_cost": 100,
                "intervention_trigger": MiracleTrigger.INCAPACITATED,
                "favor_threshold": 50,
                "narrative_text": "[PLACEHOLDER] A protective light surrounds the faithful.",
            },
        )
