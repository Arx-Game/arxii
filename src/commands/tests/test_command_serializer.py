"""Tests for command serialization."""

from unittest.mock import MagicMock

from django.test import TestCase

from commands.evennia_overrides.builder import CmdDig
from commands.evennia_overrides.perception import CmdLook
from commands.serializers import CommandSerializer
from commands.utils import serialize_cmdset


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
