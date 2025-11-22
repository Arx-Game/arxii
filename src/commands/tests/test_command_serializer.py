from typing import ClassVar
from unittest.mock import MagicMock

from django.test import TestCase

from commands.command import ArxCommand
from commands.dispatchers import TargetDispatcher
from commands.evennia_overrides.builder import CmdDig
from commands.handlers.base import BaseHandler
from commands.serializers import CommandSerializer
from commands.utils import serialize_cmdset


class DummyHandler(BaseHandler):
    def __init__(self):
        super().__init__(flow_name="test_flow")

    def run(self, **kwargs):
        pass


class DummyDispatcherCommand(ArxCommand):
    key = "dummy"
    dispatchers: ClassVar[list[TargetDispatcher]] = [
        TargetDispatcher(r"^(?P<target>.+)$", DummyHandler())
    ]


class CommandSerializerTests(TestCase):
    """Tests for serializing commands into payload dictionaries."""

    def test_builder_command_serialization(self):
        """Serializer should return mixin payload for builder commands."""
        serializer = CommandSerializer(CmdDig())
        assert serializer.data["descriptors"] == CmdDig().to_payload()["descriptors"]

    def test_dispatcher_command_serialization(self):
        """Serializer should use dispatchers to build payload."""
        cmd = DummyDispatcherCommand()
        serializer = CommandSerializer(cmd)
        assert serializer.data["descriptors"] == cmd.to_payload()["descriptors"]
        desc = serializer.data["descriptors"][0]
        assert "target" in desc["params_schema"]
        assert desc["prompt"] == "dummy <target>"

    def test_serialize_cmdset_combines_commands(self):
        """serialize_cmdset should aggregate descriptors from cmdset."""
        cmdset = MagicMock()
        cmdset.commands = [CmdDig(), DummyDispatcherCommand()]
        obj = MagicMock()
        obj.cmdset.current = cmdset
        data = serialize_cmdset(obj)
        actions = {d["action"] for d in data}
        assert "@dig" in actions
        assert "dummy" in actions

    def test_serialize_cmdset_filters_by_access(self):
        """serialize_cmdset should only include commands the user has access to."""
        # Create a mock command that denies access
        restricted_cmd = MagicMock()
        restricted_cmd.key = "restricted"
        restricted_cmd.access.return_value = False
        restricted_cmd.to_payload.return_value = {
            "descriptors": [{"action": "restricted", "params_schema": {}}],
        }

        # Create a mock command that allows access
        allowed_cmd = MagicMock()
        allowed_cmd.key = "allowed"
        allowed_cmd.access.return_value = True
        allowed_cmd.to_payload.return_value = {
            "descriptors": [{"action": "allowed", "params_schema": {}}],
        }

        # Set up cmdset with both commands
        cmdset = MagicMock()
        cmdset.commands = [restricted_cmd, allowed_cmd]
        obj = MagicMock()
        obj.cmdset.current = cmdset

        # Serialize and verify only allowed command is included
        data = serialize_cmdset(obj)
        actions = {d["action"] for d in data}

        assert "restricted" not in actions
        assert "allowed" in actions

        # Verify access was checked with correct parameters
        restricted_cmd.access.assert_called_with(obj, "cmd")
        allowed_cmd.access.assert_called_with(obj, "cmd")
