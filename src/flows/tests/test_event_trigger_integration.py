from unittest.mock import patch

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from flows.consts import FlowActionChoices
from flows.factories import (
    FlowDefinitionFactory,
    FlowExecutionFactory,
    FlowStepDefinitionFactory,
    TriggerDefinitionFactory,
    TriggerFactory,
)
from flows.flow_stack import FlowStack


class FlowEventTriggerIntegrationTests(TestCase):
    def test_glance_event_triggers_match_caller_and_target(self):
        room = ObjectDBFactory(
            db_key="hall", db_typeclass_path="typeclasses.rooms.Room"
        )
        caller = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        target = ObjectDBFactory(
            db_key="Bob",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )

        look_flow = FlowDefinitionFactory()
        FlowStepDefinitionFactory(
            flow=look_flow,
            action=FlowActionChoices.EMIT_FLOW_EVENT,
            variable_name="glance",
            parameters={
                "event_type": "glance",
                "data": {"caller": "$caller.pk", "target": "$target.pk"},
            },
        )

        fx = FlowExecutionFactory(
            flow_definition=look_flow,
            variable_mapping={"caller": caller, "target": target},
            flow_stack=FlowStack(trigger_registry=room.trigger_registry),
            origin=caller,
        )
        for obj in (room, caller, target):
            fx.context.initialize_state_for_object(obj)

        trigdef_caller = TriggerDefinitionFactory(
            event__name="glance", base_filter_condition={"caller": caller.pk}
        )
        trigger_caller = TriggerFactory(trigger_definition=trigdef_caller, obj=caller)

        trigdef_target = TriggerDefinitionFactory(
            event__name="glance", base_filter_condition={"target": target.pk}
        )
        trigger_target = TriggerFactory(trigger_definition=trigdef_target, obj=target)

        trigdef_wrong = TriggerDefinitionFactory(
            event__name="glance", base_filter_condition={"target": caller.pk}
        )
        trigger_wrong = TriggerFactory(trigger_definition=trigdef_wrong, obj=caller)

        registry = room.trigger_registry
        for trig in (trigger_caller, trigger_target, trigger_wrong):
            registry.register_trigger(trig)

        with patch.object(FlowStack, "create_and_execute_flow") as mock_create:
            fx.flow_stack.execute_flow(fx)

            self.assertEqual(mock_create.call_count, 2)
            called_origins = {
                call.kwargs.get("origin") for call in mock_create.call_args_list
            }
            self.assertIn(trigger_caller, called_origins)
            self.assertIn(trigger_target, called_origins)
            self.assertNotIn(trigger_wrong, called_origins)

        event = fx.context.flow_events["glance"]
        self.assertEqual(event.data["caller"], caller.pk)
        self.assertEqual(event.data["target"], target.pk)

    def test_self_placeholder_in_filter_matches_trigger_object(self):
        room = ObjectDBFactory(
            db_key="hall", db_typeclass_path="typeclasses.rooms.Room"
        )
        caller = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        target = ObjectDBFactory(
            db_key="Bob",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )

        look_flow = FlowDefinitionFactory()
        FlowStepDefinitionFactory(
            flow=look_flow,
            action=FlowActionChoices.EMIT_FLOW_EVENT,
            variable_name="glance",
            parameters={
                "event_type": "glance",
                "data": {"caller": "$caller.pk", "target": "$target.pk"},
            },
        )

        fx = FlowExecutionFactory(
            flow_definition=look_flow,
            variable_mapping={"caller": caller, "target": target},
            flow_stack=FlowStack(trigger_registry=room.trigger_registry),
            origin=caller,
        )
        for obj in (room, caller, target):
            fx.context.initialize_state_for_object(obj)

        tdef_self = TriggerDefinitionFactory(
            event__name="glance", base_filter_condition={"target": "$self"}
        )
        trigger_self = TriggerFactory(trigger_definition=tdef_self, obj=target)

        tdef_wrong = TriggerDefinitionFactory(
            event__name="glance", base_filter_condition={"target": "$self"}
        )
        trigger_wrong = TriggerFactory(trigger_definition=tdef_wrong, obj=caller)

        registry = room.trigger_registry
        for trig in (trigger_self, trigger_wrong):
            registry.register_trigger(trig)

        with patch.object(FlowStack, "create_and_execute_flow") as mock_create:
            fx.flow_stack.execute_flow(fx)

            self.assertEqual(mock_create.call_count, 1)
            called_origin = mock_create.call_args.kwargs.get("origin")
            self.assertEqual(called_origin, trigger_self)
