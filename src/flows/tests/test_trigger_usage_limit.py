from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from flows.consts import FlowActionChoices
from flows.factories import (
    FlowDefinitionFactory,
    FlowExecutionFactory,
    FlowStepDefinitionFactory,
    SceneDataManagerFactory,
    TriggerDefinitionFactory,
    TriggerFactory,
)
from flows.flow_stack import FlowStack
from flows.models.triggers import TriggerData


class TriggerUsageLimitTests(TestCase):
    def test_usage_limit_prevents_repeated_name_change(self):
        room = ObjectDBFactory(
            db_key="hall", db_typeclass_path="typeclasses.rooms.Room"
        )
        viewer = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        target = ObjectDBFactory(
            db_key="Eve",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )

        # Flow that emits a glance event
        look_flow = FlowDefinitionFactory()
        FlowStepDefinitionFactory(
            flow=look_flow,
            action=FlowActionChoices.EMIT_FLOW_EVENT,
            variable_name="glance",
            parameters={"event_type": "glance", "data": {"target": "$target"}},
        )

        # Flow that appends " (Evil)" to target name
        evil_flow = FlowDefinitionFactory()
        FlowStepDefinitionFactory(
            flow=evil_flow,
            action=FlowActionChoices.CALL_SERVICE_FUNCTION,
            variable_name="append_to_attribute",
            parameters={
                "obj": "$event.data.target",
                "attribute": "name",
                "append_text": " (Evil)",
            },
        )

        tdef = TriggerDefinitionFactory(
            event__key="glance",
            flow_definition=evil_flow,
            base_filter_condition={},
        )
        trigger = TriggerFactory(trigger_definition=tdef, obj=viewer)
        TriggerData.objects.create(trigger=trigger, key="usage_limit_glance", value="1")

        registry = room.trigger_registry
        registry.register_trigger(trigger)

        context = SceneDataManagerFactory()
        stack = FlowStack(trigger_registry=registry)
        for obj in (room, viewer, target):
            context.initialize_state_for_object(obj)

        # Execute look flow twice
        for _ in range(2):
            fx = FlowExecutionFactory(
                flow_definition=look_flow,
                variable_mapping={"target": target},
                flow_stack=stack,
                context=context,
                origin=viewer,
            )
            stack.execute_flow(fx)

        state = context.get_state_by_pk(target.pk)
        self.assertEqual(state.name, f"{target.key} (Evil)")
        event = context.flow_events["glance"]
        self.assertEqual(context.get_trigger_fire_count(trigger.id, event.usage_key), 1)

    def test_default_usage_limit_is_one(self):
        room = ObjectDBFactory(
            db_key="hall", db_typeclass_path="typeclasses.rooms.Room"
        )
        viewer = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        target = ObjectDBFactory(
            db_key="Eve",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )

        look_flow = FlowDefinitionFactory()
        FlowStepDefinitionFactory(
            flow=look_flow,
            action=FlowActionChoices.EMIT_FLOW_EVENT,
            variable_name="glance",
            parameters={"event_type": "glance", "data": {"target": "$target"}},
        )

        evil_flow = FlowDefinitionFactory()
        FlowStepDefinitionFactory(
            flow=evil_flow,
            action=FlowActionChoices.CALL_SERVICE_FUNCTION,
            variable_name="append_to_attribute",
            parameters={
                "obj": "$event.data.target",
                "attribute": "name",
                "append_text": " (Evil)",
            },
        )

        tdef = TriggerDefinitionFactory(
            event__key="glance", flow_definition=evil_flow, base_filter_condition={}
        )
        trigger = TriggerFactory(trigger_definition=tdef, obj=viewer)

        registry = room.trigger_registry
        registry.register_trigger(trigger)

        context = SceneDataManagerFactory()
        stack = FlowStack(trigger_registry=registry)
        for obj in (room, viewer, target):
            context.initialize_state_for_object(obj)

        for _ in range(2):
            fx = FlowExecutionFactory(
                flow_definition=look_flow,
                variable_mapping={"target": target},
                flow_stack=stack,
                context=context,
                origin=viewer,
            )
            stack.execute_flow(fx)

        state = context.get_state_by_pk(target.pk)
        self.assertEqual(state.name, f"{target.key} (Evil)")
        event = context.flow_events["glance"]
        self.assertEqual(context.get_trigger_fire_count(trigger.id, event.usage_key), 1)

    def test_zero_usage_limit_allows_unlimited_triggers(self):
        room = ObjectDBFactory(
            db_key="hall", db_typeclass_path="typeclasses.rooms.Room"
        )
        viewer = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        target = ObjectDBFactory(
            db_key="Eve",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )

        look_flow = FlowDefinitionFactory()
        FlowStepDefinitionFactory(
            flow=look_flow,
            action=FlowActionChoices.EMIT_FLOW_EVENT,
            variable_name="glance",
            parameters={"event_type": "glance", "data": {"target": "$target"}},
        )

        evil_flow = FlowDefinitionFactory()
        FlowStepDefinitionFactory(
            flow=evil_flow,
            action=FlowActionChoices.CALL_SERVICE_FUNCTION,
            variable_name="append_to_attribute",
            parameters={
                "obj": "$event.data.target",
                "attribute": "name",
                "append_text": " (Evil)",
            },
        )

        tdef = TriggerDefinitionFactory(
            event__key="glance", flow_definition=evil_flow, base_filter_condition={}
        )
        trigger = TriggerFactory(trigger_definition=tdef, obj=viewer)
        TriggerData.objects.create(trigger=trigger, key="usage_limit_glance", value="0")

        registry = room.trigger_registry
        registry.register_trigger(trigger)

        context = SceneDataManagerFactory()
        stack = FlowStack(trigger_registry=registry)
        for obj in (room, viewer, target):
            context.initialize_state_for_object(obj)

        for _ in range(2):
            fx = FlowExecutionFactory(
                flow_definition=look_flow,
                variable_mapping={"target": target},
                flow_stack=stack,
                context=context,
                origin=viewer,
            )
            stack.execute_flow(fx)

        state = context.get_state_by_pk(target.pk)
        self.assertEqual(state.name, f"{target.key} (Evil) (Evil)")
        event = context.flow_events["glance"]
        self.assertEqual(context.get_trigger_fire_count(trigger.id, event.usage_key), 2)
