from unittest.mock import MagicMock

from django.test import TestCase

from commands.command import ArxCommand
from commands.dispatchers import TargetDispatcher
from commands.evennia_overrides.builder import CmdDig
from commands.serializers import CommandSerializer
from commands.utils import serialize_cmdset


class DummyHandler:
    def run(self, **kwargs):
        pass


class DummyDispatcherCommand(ArxCommand):
    key = "dummy"
    dispatchers = [TargetDispatcher(r"^(?P<target>.+)$", DummyHandler())]


class CommandSerializerTests(TestCase):
    """Tests for serializing commands into payload dictionaries."""

    def test_builder_command_serialization(self):
        """Serializer should return mixin payload for builder commands."""
        serializer = CommandSerializer(CmdDig())
        self.assertEqual(
            serializer.data["descriptors"], CmdDig().to_payload()["descriptors"]
        )

    def test_dispatcher_command_serialization(self):
        """Serializer should use dispatchers to build payload."""
        cmd = DummyDispatcherCommand()
        serializer = CommandSerializer(cmd)
        self.assertEqual(
            serializer.data["descriptors"], cmd.to_payload()["descriptors"]
        )
        desc = serializer.data["descriptors"][0]
        self.assertIn("target", desc["params_schema"])
        self.assertEqual(desc["prompt"], "dummy <target>")

    def test_serialize_cmdset_combines_commands(self):
        """serialize_cmdset should aggregate descriptors from cmdset."""
        cmdset = MagicMock()
        cmdset.commands = [CmdDig(), DummyDispatcherCommand()]
        obj = MagicMock()
        obj.cmdset.current = cmdset
        data = serialize_cmdset(obj)
        actions = {d["action"] for d in data}
        self.assertIn("@dig", actions)
        self.assertIn("dummy", actions)
