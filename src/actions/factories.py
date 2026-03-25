"""FactoryBoy factories for actions app models."""

from __future__ import annotations

import factory
from factory.django import DjangoModelFactory

from actions.constants import ActionTargetType, GateRole, Pipeline
from actions.models import ActionTemplate, ActionTemplateGate, ConsequencePool, ConsequencePoolEntry


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
