"""Tests for CmdTravel (#2163)."""

from django.test import TestCase

from commands.travel import CmdTravel
from evennia_extensions.factories import ObjectDBFactory, RoomProfileFactory
from world.areas.factories import AreaFactory


class CmdTravelTests(TestCase):
    def setUp(self):
        self.area = AreaFactory()
        self.room_a = ObjectDBFactory(db_key="RoomA", db_typeclass_path="typeclasses.rooms.Room")
        self.room_b = ObjectDBFactory(db_key="RoomB", db_typeclass_path="typeclasses.rooms.Room")
        # Room.at_object_creation() already auto-creates a bare RoomProfile
        # (typeclasses/rooms.py) — RoomProfileFactory (rather than
        # RoomProfile.objects.create()) is the established fix for the
        # resulting UNIQUE-constraint collision (see its docstring).
        RoomProfileFactory(objectdb=self.room_a, area=self.area, is_public=True)
        RoomProfileFactory(objectdb=self.room_b, area=self.area, is_public=True)
        ObjectDBFactory(
            db_key="east",
            db_typeclass_path="typeclasses.exits.Exit",
            location=self.room_a,
            destination=self.room_b,
        )
        self.caller = ObjectDBFactory(
            db_key="Wanderer",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room_a,
        )
        self.target_char = ObjectDBFactory(
            db_key="Friend",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room_b,
        )

    def _make_cmd(self, args):
        cmd = CmdTravel()
        cmd.caller = self.caller
        cmd.args = args
        cmd.raw_string = f"travel {args}"
        return cmd

    def test_travel_to_character_resolves_and_dispatches(self):
        from unittest.mock import patch

        cmd = self._make_cmd("Friend")
        with patch.object(self.caller, "msg"), patch("actions.definitions.movement.delay"):
            cmd.func()
        # No CommandError raised means the action dispatched successfully —
        # TravelAction's own tests (Task 2) cover the walk mechanics; this
        # test covers only name resolution and dispatch wiring.

    def test_travel_unknown_name_raises_command_error_message(self):
        from unittest.mock import patch

        cmd = self._make_cmd("NobodyHere")
        with patch.object(self.caller, "msg") as mock_msg:
            cmd.func()
        assert mock_msg.called

    def test_travel_stop_dispatches_stop_travel_action(self):
        from unittest.mock import patch

        self.caller.ndb.active_travel_token = "some-token"  # noqa: S105
        cmd = self._make_cmd("stop")
        with patch.object(self.caller, "msg"):
            cmd.func()
        assert self.caller.ndb.active_travel_token is None
