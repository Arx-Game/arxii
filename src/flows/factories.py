import factory

from flows import models
from flows.context_data import ContextData


class FlowDefinitionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.FlowDefinition

    name = factory.Sequence(lambda n: f"TestFlow{n}")
    description = factory.Faker("sentence")


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


class TriggerDefinitionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.TriggerDefinition

    name = factory.Sequence(lambda n: f"TriggerDef{n}")
    flow_definition = factory.SubFactory(FlowDefinitionFactory)
    event_type = factory.Faker("word")
    filter_condition = factory.LazyFunction(dict)


class TriggerFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.Trigger

    trigger_definition = factory.SubFactory(TriggerDefinitionFactory)
    obj = factory.Faker("pyint")  # Replace with actual object factory if needed
    additional_filter_condition = factory.LazyFunction(dict)


# ContextData is not a model, but we can provide a helper for tests
class ContextDataFactory(factory.Factory):
    class Meta:
        model = ContextData

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        return model_class()
