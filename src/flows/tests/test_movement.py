from django.test import TestCase
import pytest

from commands.exceptions import CommandError
from evennia_extensions.factories import ObjectDBFactory
from flows.consts import FlowActionChoices
from flows.factories import (
    FlowDefinitionFactory,
    FlowExecutionFactory,
    FlowStepDefinitionFactory,
)
from flows.scene_data_manager import SceneDataManager
from flows.service_functions.movement import move_object


class MoveObjectServiceFunctionTests(TestCase):
    def test_move_object_updates_location(self):
        room1 = ObjectDBFactory(
            db_key="room1",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        room2 = ObjectDBFactory(
            db_key="room2",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        item = ObjectDBFactory(db_key="rock", location=room1)

        sdm = SceneDataManager()
        item_state = sdm.initialize_state_for_object(item)
        dest_state = sdm.initialize_state_for_object(room2)
        sdm.initialize_state_for_object(room1)

        move_object(item_state, dest_state)

        item.refresh_from_db()
        assert item.location == room2

    def test_invalid_destination_raises(self):
        room = ObjectDBFactory(
            db_key="room",
            db_typeclass_path="typeclasses.rooms.Room",
        )

        sdm = SceneDataManager()
        room_state = sdm.initialize_state_for_object(room)

        # can_move returns False when moving a room
        with pytest.raises(CommandError):
            move_object(room_state, room_state)

    def test_can_move_is_checked(self):
        room1 = ObjectDBFactory(
            db_key="r1",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        room2 = ObjectDBFactory(
            db_key="r2",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        sdm = SceneDataManager()
        room1_state = sdm.initialize_state_for_object(room1)
        room2_state = sdm.initialize_state_for_object(room2)

        with pytest.raises(CommandError):
            move_object(room1_state, room2_state)

    def test_flowstep_moves_object(self):
        """Integration test: flow step resolves variables and calls service function."""
        room1 = ObjectDBFactory(
            db_key="start",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        room2 = ObjectDBFactory(
            db_key="end",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        item = ObjectDBFactory(db_key="rock", location=room1)

        flow_def = FlowDefinitionFactory()
        FlowStepDefinitionFactory(
            flow=flow_def,
            action=FlowActionChoices.CALL_SERVICE_FUNCTION,
            variable_name="move_object",
            parameters={"obj": "@item", "destination": "@dest"},
        )

        fx = FlowExecutionFactory(
            flow_definition=flow_def,
            variable_mapping={"item": item, "dest": room2},
        )
        for obj in (room1, room2, item):
            fx.context.initialize_state_for_object(obj)

        fx.flow_stack.execute_flow(fx)

        item.refresh_from_db()
        assert item.location == room2
