from unittest.mock import patch

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from flows.consts import FlowActionChoices
from flows.factories import (
    FlowDefinitionFactory,
    FlowExecutionFactory,
    FlowStepDefinitionFactory,
)
from flows.scene_data_manager import SceneDataManager
from flows.service_functions.perception import get_formatted_description


class FlowExecutionServiceFunctionTests(TestCase):
    def test_get_service_function_returns_callable(self):
        fx = FlowExecutionFactory()
        func = fx.get_service_function("get_formatted_description")
        assert func is get_formatted_description

    def test_execute_call_service_function_integration(self):
        flow_def = FlowDefinitionFactory()
        FlowStepDefinitionFactory(
            flow=flow_def,
            action=FlowActionChoices.CALL_SERVICE_FUNCTION,
            variable_name="get_formatted_description",
            parameters={
                "obj": "@target",
                "mode": "look",
                "result_variable": "desc",
            },
        )

        sword = ObjectDBFactory(db_key="sword")
        sword.db.desc = "A shiny sword"
        viewer = ObjectDBFactory(db_key="viewer")

        fx = FlowExecutionFactory(
            flow_definition=flow_def,
            variable_mapping={"target": sword},
        )
        fx.context.initialize_state_for_object(sword)
        fx.context.initialize_state_for_object(viewer)

        fx.execute_current_step()

        expected = fx.context.get_state_by_pk(sword.pk).return_appearance()
        assert fx.get_variable("desc") == expected

    def test_room_description_format(self):
        flow_def = FlowDefinitionFactory()
        FlowStepDefinitionFactory(
            flow=flow_def,
            action=FlowActionChoices.CALL_SERVICE_FUNCTION,
            variable_name="get_formatted_description",
            parameters={
                "obj": "@target",
                "mode": "look",
                "result_variable": "desc",
            },
        )

        room = ObjectDBFactory(
            db_key="Hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        room.db.desc = "A simple room."
        dest = ObjectDBFactory(
            db_key="Outside",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        exit_obj = ObjectDBFactory(
            db_key="out",
            db_typeclass_path="typeclasses.exits.Exit",
            location=room,
            destination=dest,
        )
        thing = ObjectDBFactory(db_key="rock", location=room)
        viewer = ObjectDBFactory(db_key="Bob", location=room)

        fx = FlowExecutionFactory(
            flow_definition=flow_def,
            variable_mapping={"target": room},
        )
        for obj in (room, dest, exit_obj, thing, viewer):
            fx.context.initialize_state_for_object(obj)

        fx.execute_current_step()

        expected = fx.context.get_state_by_pk(room.pk).return_appearance()
        assert fx.get_variable("desc") == expected

    def test_send_message_accepts_state(self):
        """Test send_message directly with BaseState objects."""
        viewer = ObjectDBFactory(db_key="viewer")
        sdm = SceneDataManager()
        state = sdm.initialize_state_for_object(viewer)

        from flows.service_functions.communication import send_message

        with patch.object(viewer, "msg") as mock_msg:
            send_message(state, "hello")
            mock_msg.assert_called_with("hello")

    def test_send_message_with_caller_and_target(self):
        """Test send_message with caller/target for pronoun resolution."""
        viewer = ObjectDBFactory(db_key="viewer")
        caller = ObjectDBFactory(db_key="Alice")
        sdm = SceneDataManager()
        viewer_state = sdm.initialize_state_for_object(viewer)
        caller_state = sdm.initialize_state_for_object(caller)

        from flows.service_functions.communication import send_message

        with patch.object(viewer, "msg") as mock_msg:
            send_message(viewer_state, "hello", caller=caller_state)
            mock_msg.assert_called_once()
