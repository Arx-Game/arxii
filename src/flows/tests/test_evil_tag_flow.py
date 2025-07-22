from unittest.mock import MagicMock, patch

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from flows.consts import FlowActionChoices
from flows.factories import (
    FlowDefinitionFactory,
    FlowExecutionFactory,
    FlowStepDefinitionFactory,
)
from flows.flow_stack import FlowStack


class TestEvilNameFlow(TestCase):
    def test_iterate_and_mark_evil(self):
        room = ObjectDBFactory(
            db_key="Hall", db_typeclass_path="typeclasses.rooms.Room"
        )
        good = ObjectDBFactory(
            db_key="Bob",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        evil = ObjectDBFactory(
            db_key="Eve",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        evil.tags.add("evil")
        viewer = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )

        # Flow to iterate contents and emit events
        look_flow = FlowDefinitionFactory()
        FlowStepDefinitionFactory(
            flow=look_flow,
            action=FlowActionChoices.EMIT_FLOW_EVENT_FOR_EACH,
            variable_name="glance",
            parameters={
                "iterable": "$room.contents",
                "event_type": "glance",
                "data": {"target": "$item"},
            },
        )

        # Flow triggered for each glance event
        evil_flow = FlowDefinitionFactory()
        step_check = FlowStepDefinitionFactory(
            flow=evil_flow,
            action=FlowActionChoices.CALL_SERVICE_FUNCTION,
            variable_name="object_has_tag",
            parameters={
                "obj": "$event.data.target",
                "tag": "evil",
                "result_variable": "is_evil",
            },
        )
        step_cond = FlowStepDefinitionFactory(
            flow=evil_flow,
            action=FlowActionChoices.EVALUATE_EQUALS,
            parent_id=step_check.id,
            variable_name="is_evil",
            parameters={"value": "True"},
        )
        FlowStepDefinitionFactory(
            flow=evil_flow,
            action=FlowActionChoices.CALL_SERVICE_FUNCTION,
            parent_id=step_cond.id,
            variable_name="append_to_attribute",
            parameters={
                "obj": "$event.data.target",
                "attribute": "name",
                "append_text": " (Evil)",
            },
        )

        fx = FlowExecutionFactory(
            flow_definition=look_flow,
            variable_mapping={"room": room},
            flow_stack=FlowStack(trigger_registry=MagicMock()),
        )
        for obj in (room, good, evil, viewer):
            fx.context.initialize_state_for_object(obj)

        # Execute the look flow to generate events
        flow_stack: FlowStack = fx.flow_stack
        flow_stack.execute_flow(fx)

        # Manually execute evil_flow for each emitted event
        for event in fx.context.flow_events.values():
            flow_stack.create_and_execute_flow(
                flow_definition=evil_flow,
                context=fx.context,
                origin=event,
                variable_mapping={"event": event},
            )

        good_state = fx.context.get_state_by_pk(good.pk)
        evil_state = fx.context.get_state_by_pk(evil.pk)

        self.assertEqual(good_state.name, good.key)
        self.assertEqual(evil_state.name, f"{evil.key} (Evil)")
        self.assertIn("glance_0", fx.context.flow_events)
        self.assertIn("glance_1", fx.context.flow_events)

        get_desc = fx.get_service_function("get_formatted_description")
        send_msg = fx.get_service_function("send_message")
        fx.set_variable("temp_target", evil)
        fx.set_variable("viewer", viewer)
        description = get_desc(fx, "$temp_target")

        with patch.object(viewer, "msg") as mock_msg:
            send_msg(fx, "$viewer", description)
            mock_msg.assert_called_with(description)

        self.assertIn("Eve (Evil)", description)
