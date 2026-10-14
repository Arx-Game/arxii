"""Tests for command serialization."""

from unittest.mock import MagicMock

from django.test import TestCase

from commands.evennia_overrides.builder import CmdDig
from commands.evennia_overrides.perception import CmdLook
from commands.serializers import CommandSerializer
from commands.utils import command_names, commands_frame, serialize_cmdset
from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory


class CommandSerializerTests(TestCase):
    def test_action_command_serialization(self):
        """Serializer should use to_payload() for action-based commands."""
        cmd = CmdLook()
        serializer = CommandSerializer(cmd)
        data = serializer.data
        assert data["key"] == "look"
        assert len(data["descriptors"]) == 1
        assert data["descriptors"][0]["action"] == "look"

    def test_builder_command_serialization(self):
        """Serializer should return mixin payload for builder commands."""
        serializer = CommandSerializer(CmdDig())
        data = serializer.data
        assert data["key"] == "@dig"

    def test_serialize_cmdset_combines_commands(self):
        """serialize_cmdset should aggregate descriptors from cmdset."""
        cmdset = MagicMock()
        cmdset.commands = [CmdDig(), CmdLook()]
        obj = MagicMock()
        obj.cmdset.current = cmdset
        data = serialize_cmdset(obj)
        actions = {d["action"] for d in data}
        assert "@dig" in actions
        assert "look" in actions

    def test_serialize_cmdset_filters_by_access(self):
        """serialize_cmdset should only include commands the user has access to."""
        restricted_cmd = MagicMock()
        restricted_cmd.key = "restricted"
        restricted_cmd.access.return_value = False
        restricted_cmd.to_payload.return_value = {
            "descriptors": [{"action": "restricted", "params_schema": {}}],
        }

        allowed_cmd = MagicMock()
        allowed_cmd.key = "allowed"
        allowed_cmd.access.return_value = True
        allowed_cmd.to_payload.return_value = {
            "descriptors": [{"action": "allowed", "params_schema": {}}],
        }

        cmdset = MagicMock()
        cmdset.commands = [restricted_cmd, allowed_cmd]
        obj = MagicMock()
        obj.cmdset.current = cmdset

        data = serialize_cmdset(obj)
        actions = {d["action"] for d in data}

        assert "restricted" not in actions
        assert "allowed" in actions


class CommandNamesTests(TestCase):
    """The names the web composer reads to tell ``@desc`` from ``@Nyx`` (#4346).

    Real characters with the real cmdsets: the list has to answer for the
    commands a player actually has, not for doubles that grant any lock.
    """

    @classmethod
    def setUpTestData(cls):
        cls.room = ObjectDBFactory(db_key="NamesRoom", db_typeclass_path="typeclasses.rooms.Room")
        cls.player_account = AccountFactory(username="names_player")
        cls.player = CharacterFactory(db_key="NamesPlayer", location=cls.room)
        cls.player.db_account = cls.player_account
        cls.player.save()
        cls.staff_account = AccountFactory(username="names_staff")
        cls.staff_account.permissions.add("Admin")
        cls.staffer = CharacterFactory(db_key="NamesStaffer", location=cls.room)
        cls.staffer.db_account = cls.staff_account
        cls.staffer.save()

    def test_names_cover_commands_with_no_web_form(self):
        names = set(command_names(self.player))

        assert {"pose", "say", "who", "look"} <= names

    def test_names_are_compared_without_their_prefix(self):
        """``+friend`` answers to ``friend`` and the account's ``@sheet`` to ``sheet``."""
        names = set(command_names(self.player))

        assert "friend" in names
        assert "sheet" in names
        assert not any(name[0] in "@&/+" for name in names)

    def test_a_player_does_not_get_a_staff_command(self):
        assert "desc" not in command_names(self.player)

    def test_staff_get_the_staff_commands(self):
        assert "desc" in command_names(self.staffer)

    def test_evennia_system_commands_are_left_out(self):
        assert not [name for name in command_names(self.player) if name.startswith("__")]

    def test_the_frame_carries_the_descriptors_and_the_names(self):
        descriptors, kwargs = commands_frame(self.player)

        assert descriptors == serialize_cmdset(self.player)
        assert kwargs == {"names": command_names(self.player)}

    def test_the_wire_frame_is_descriptors_then_names(self):
        """Through Evennia's own serializer and the webclient protocol, as the client reads it."""
        import json

        from evennia.server.portal.webclient import WebSocketClient
        from evennia.server.sessionhandler import ServerSessionHandler

        session = MagicMock(protocol_flags={"ENCODING": "utf-8"})
        messages = ServerSessionHandler().clean_senddata(
            session, {"commands": commands_frame(self.player)}
        )
        portal = MagicMock()
        for message_type, (args, kwargs) in messages.items():
            WebSocketClient.send_default(portal, message_type, *args, **kwargs)

        frame = json.loads(portal.sendLine.call_args.args[0])
        assert frame[0] == "commands"
        assert isinstance(frame[1], list)
        assert frame[1]
        assert frame[2]["names"] == command_names(self.player)
