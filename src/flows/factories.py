from typing import Dict, Optional

import factory

from evennia_extensions.factories import ObjectDBFactory
from flows import models
from flows.context_data import ContextData
from flows.flow_event import FlowEvent
from flows.flow_execution import FlowExecution
from flows.flow_stack import FlowStack


class FlowDefinitionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.FlowDefinition

    name = factory.Sequence(lambda n: f"TestFlow{n}")
    description = factory.Faker("sentence")

    class Params:
        with_step = False
        step_action = models.FlowActionChoices.SET_CONTEXT_VALUE
        step_parameters = factory.LazyFunction(dict)

    @factory.post_generation
    def create_initial_step(self, create, extracted, **kwargs):
        """Post-generation hook to create an initial step for the flow definition.

        Args:
            create: Whether to create the step
            extracted: If a dict, can contain 'with_step', 'step_action', and 'step_parameters'.
                     If True, creates a step with defaults. If False, doesn't create a step.
        """
        if not create:
            return

        # Default values
        step_action = models.FlowActionChoices.SET_CONTEXT_VALUE
        step_parameters = {}

        # Handle different types of extracted values
        if isinstance(extracted, dict):
            with_step = extracted.get(
                "with_step", True
            )  # Default to True if not specified
            step_action = extracted.get("step_action", step_action)
            step_parameters = extracted.get("step_parameters", step_parameters)
        else:
            # If extracted is not a dict, treat it as a boolean flag
            with_step = (
                extracted if extracted is not None else True
            )  # Default to True if None

        if with_step:
            FlowStepDefinitionFactory(
                flow=self,
                action=step_action,
                parameters=step_parameters,
                variable_name="initial_step",
            )


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

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        return model_class()


class FlowStackFactory(factory.Factory):
    """Factory for creating FlowStack instances for testing."""

    class Meta:
        model = FlowStack

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        """Create an instance of the model."""
        return FlowStack()


class FlowExecutionFactory(factory.Factory):
    """Factory for creating FlowExecution instances for testing."""

    class Meta:
        model = FlowExecution

    flow_definition = None
    context = None
    flow_stack = None
    origin = None
    variable_mapping = factory.LazyFunction(dict)

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        """Create an instance of the model, and save it to the database if needed."""
        from unittest.mock import MagicMock

        # Handle defaults
        if kwargs.get("flow_definition") is None:
            # Create a flow definition with an initial step
            kwargs["flow_definition"] = FlowDefinitionFactory(create_initial_step=True)

        if kwargs.get("context") is None:
            kwargs["context"] = ContextDataFactory()

        if kwargs.get("flow_stack") is None:
            kwargs["flow_stack"] = FlowStackFactory()

        if kwargs.get("origin") is None:
            kwargs["origin"] = MagicMock()

        if kwargs.get("variable_mapping") is None:
            kwargs["variable_mapping"] = {}

        return model_class(
            flow_definition=kwargs["flow_definition"],
            context=kwargs["context"],
            flow_stack=kwargs["flow_stack"],
            origin=kwargs["origin"],
            variable_mapping=kwargs["variable_mapping"],
        )


class FlowEventFactory:
    """Factory for creating FlowEvent instances for testing."""

    @classmethod
    def create(
        cls,
        event_type: str = "test_event",
        source: Optional[FlowExecution] = None,
        data: Optional[Dict] = None,
    ) -> FlowEvent:
        """
        Create a new FlowEvent instance with test defaults.

        Args:
            event_type: The type of event.
            source: The source FlowExecution. If None, creates a new one.
            data: Optional event data.

        Returns:
            A new FlowEvent instance.
        """
        if source is None:
            source = FlowExecutionFactory.create()

        return FlowEvent(event_type=event_type, source=source, data=data or {})
