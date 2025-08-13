from unittest.mock import MagicMock

from django.test import TestCase

from commands.evennia_overrides.perception import CmdLook
from evennia_extensions.factories import ObjectDBFactory


class CmdLookTests(TestCase):
    def setUp(self):
        self.room = ObjectDBFactory(
            db_key="Hall", db_typeclass_path="typeclasses.rooms.Room"
        )
        self.viewer = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        self.target = ObjectDBFactory(db_key="Rock", location=self.room)
        self.viewer.msg = MagicMock()
        self.viewer.search = MagicMock(return_value=self.target)

    def test_look_at_room(self):
        cmd = CmdLook()
        cmd.caller = self.viewer
        cmd.args = ""
        cmd.raw_string = "look"
        cmd.parse()
        cmd.func()

        # The look flow should call msg twice: once for text, once for room_state
        self.assertEqual(self.viewer.msg.call_count, 2)

        # First call should be the text message
        context = cmd.selected_dispatcher.handler.context
        expected = context.get_state_by_pk(self.room.pk).return_appearance(mode="look")
        first_call = self.viewer.msg.call_args_list[0]
        self.assertEqual(first_call.args[0], expected)

        # Second call should be the room_state payload
        second_call = self.viewer.msg.call_args_list[1]
        self.assertIn("room_state", second_call.kwargs)

    def test_look_at_target(self):
        cmd = CmdLook()
        cmd.caller = self.viewer
        cmd.args = "Rock"
        cmd.raw_string = "look Rock"
        cmd.parse()
        cmd.func()

        # The look flow should call msg twice: once for text, once for room_state
        self.assertEqual(self.viewer.msg.call_count, 2)

        # First call should be the text message for the target
        context = cmd.selected_dispatcher.handler.context
        expected = context.get_state_by_pk(self.target.pk).return_appearance(
            mode="look"
        )
        first_call = self.viewer.msg.call_args_list[0]
        self.assertEqual(first_call.args[0], expected)

        # Second call should be the room_state payload
        second_call = self.viewer.msg.call_args_list[1]
        self.assertIn("room_state", second_call.kwargs)

    def test_glance_alias(self):
        cmd = CmdLook()
        cmd.caller = self.viewer
        cmd.args = ""
        cmd.raw_string = "glance"
        cmd.parse()
        cmd.cmdname = "glance"
        cmd.func()

        # The look flow should call msg twice: once for text, once for room_state
        self.assertEqual(self.viewer.msg.call_count, 2)

        # First call should be the text message
        context = cmd.selected_dispatcher.handler.context
        expected = context.get_state_by_pk(self.room.pk).return_appearance(
            mode="glance"
        )
        first_call = self.viewer.msg.call_args_list[0]
        self.assertEqual(first_call.args[0], expected)

        # Second call should be the room_state payload
        second_call = self.viewer.msg.call_args_list[1]
        self.assertIn("room_state", second_call.kwargs)
