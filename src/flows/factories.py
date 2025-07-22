from unittest.mock import MagicMock

import factory

from evennia_extensions.factories import ObjectDBFactory
from flows import models
from flows.context_data import ContextData
from flows.flow_event import FlowEvent
from flows.flow_execution import FlowExecution
from flows.flow_stack import FlowStack
from flows.trigger_registry import TriggerRegistry


class FlowDefinitionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.FlowDefinition

    name = factory.Sequence(lambda n: f"TestFlow{n}")
    description = factory.Faker("sentence")


class FlowDefinitionWithInitialStepFactory(FlowDefinitionFactory):
    @factory.post_generation
    def post_hook(self, create, extracted, **kwargs):
        if create:
            FlowStepDefinitionFactory(flow=self, variable_name="initial_step")


class FlowStepDefinitionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.FlowStepDefinition

    flow = factory.SubFactory(FlowDefinitionFactory)
    action = factory.Iterator(
        [
            models.FlowActionChoices.SET_CONTEXT_VALUE,
            models.FlowActionChoices.MODIFY_CONTEXT_VALUE,
            models.FlowActionChoices.EVALUATE_EQUALS,
            models.FlowActionChoices.CALL_SERVICE_FUNCTION,
            models.FlowActionChoices.EMIT_FLOW_EVENT,
            models.FlowActionChoices.EMIT_FLOW_EVENT_FOR_EACH,
        ]
    )
    variable_name = factory.Sequence(lambda n: f"var{n}")
    parameters = factory.LazyFunction(dict)
    parent_id = None


class EventFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.Event
        django_get_or_create = ("key",)

    key = factory.Sequence(lambda n: f"event_{n}")
    label = factory.Sequence(lambda n: f"Event {n}")


class TriggerDefinitionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.TriggerDefinition

    name = factory.Sequence(lambda n: f"TriggerDef{n}")
    flow_definition = factory.SubFactory(FlowDefinitionFactory)
    event = factory.SubFactory(EventFactory)
    base_filter_condition = factory.LazyFunction(dict)


class TriggerFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.Trigger

    trigger_definition = factory.SubFactory(TriggerDefinitionFactory)
    obj = factory.SubFactory(ObjectDBFactory)
    additional_filter_condition = factory.LazyFunction(dict)


# ContextData is not a model, but we can provide a helper for tests
class ContextDataFactory(factory.Factory):
    class Meta:
        model = ContextData


class FlowStackFactory(factory.Factory):
    """Factory for creating FlowStack instances for testing."""

    class Meta:
        model = FlowStack

    trigger_registry = factory.LazyFunction(TriggerRegistry)


class FlowExecutionFactory(factory.Factory):
    """Factory for creating FlowExecution instances for testing."""

    class Meta:
        model = FlowExecution

    flow_definition = factory.SubFactory(FlowDefinitionWithInitialStepFactory)
    context = factory.SubFactory(ContextDataFactory)
    flow_stack = factory.SubFactory(FlowStackFactory)
    origin = factory.LazyFunction(MagicMock)
    variable_mapping = factory.LazyFunction(dict)


class FlowEventFactory(factory.Factory):
    """Factory for creating FlowEvent instances for testing."""

    class Meta:
        model = FlowEvent

    event_type = "test_event"
    source = factory.SubFactory(FlowExecutionFactory)
    data = factory.LazyFunction(dict)

    class Params:
        # Allow overriding the source's context directly
        context = factory.Trait(
            source=factory.SubFactory(
                FlowExecutionFactory, context=factory.SelfAttribute("..context")
            )
        )
