from unittest.mock import MagicMock

from django.test import TestCase

from commands.look import CmdLook
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
        context = cmd.selected_dispatcher.handler.context
        expected = context.get_state_by_pk(self.room.pk).return_appearance(mode="look")
        self.viewer.msg.assert_called_with(expected)

    def test_look_at_target(self):
        cmd = CmdLook()
        cmd.caller = self.viewer
        cmd.args = "Rock"
        cmd.raw_string = "look Rock"
        cmd.parse()
        cmd.func()
        context = cmd.selected_dispatcher.handler.context
        expected = context.get_state_by_pk(self.target.pk).return_appearance(
            mode="look"
        )
        self.viewer.msg.assert_called_with(expected)

    def test_glance_alias(self):
        cmd = CmdLook()
        cmd.caller = self.viewer
        cmd.args = ""
        cmd.raw_string = "glance"
        cmd.parse()
        cmd.cmdname = "glance"
        cmd.func()
        context = cmd.selected_dispatcher.handler.context
        expected = context.get_state_by_pk(self.room.pk).return_appearance(
            mode="glance"
        )
        self.viewer.msg.assert_called_with(expected)
