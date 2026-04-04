"""FactoryBoy factories for actions app models."""

from __future__ import annotations

import factory
from factory.django import DjangoModelFactory

from actions.constants import ActionTargetType, EnhancementSourceType, GateRole, Pipeline
from actions.models import (
    ActionEnhancement,
    ActionTemplate,
    ActionTemplateGate,
    ConsequencePool,
    ConsequencePoolEntry,
)


class ConsequencePoolFactory(DjangoModelFactory):
    """Factory for ConsequencePool."""

    class Meta:
        model = ConsequencePool

    name = factory.Sequence(lambda n: f"Pool{n}")
    description = ""
    parent = None


class ConsequencePoolEntryFactory(DjangoModelFactory):
    """Factory for ConsequencePoolEntry."""

    class Meta:
        model = ConsequencePoolEntry

    pool = factory.SubFactory(ConsequencePoolFactory)
    consequence = factory.SubFactory("world.checks.factories.ConsequenceFactory")
    weight_override = None
    is_excluded = False


class ActionTemplateFactory(DjangoModelFactory):
    """Factory for ActionTemplate."""

    class Meta:
        model = ActionTemplate
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Template{n}")
    description = ""
    check_type = factory.SubFactory("world.checks.factories.CheckTypeFactory")
    consequence_pool = None
    pipeline = Pipeline.SINGLE
    target_type = ActionTargetType.SELF
    icon = ""
    category = "test"


class ActionEnhancementFactory(DjangoModelFactory):
    """Factory for ActionEnhancement with technique source."""

    class Meta:
        model = ActionEnhancement

    base_action_key = "intimidate"
    variant_name = factory.Sequence(lambda n: f"Enhanced Action {n}")
    is_involuntary = False
    source_type = EnhancementSourceType.TECHNIQUE
    technique = factory.SubFactory("world.magic.factories.TechniqueFactory")
    distinction = None
    condition = None


class ActionTemplateGateFactory(DjangoModelFactory):
    """Factory for ActionTemplateGate."""

    class Meta:
        model = ActionTemplateGate

    action_template = factory.SubFactory(ActionTemplateFactory, pipeline=Pipeline.GATED)
    gate_role = GateRole.ACTIVATION
    step_order = 0
    check_type = factory.SubFactory("world.checks.factories.CheckTypeFactory")
    consequence_pool = factory.SubFactory(ConsequencePoolFactory)
    failure_aborts = True
