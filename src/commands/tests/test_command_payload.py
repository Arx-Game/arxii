from django.test import TestCase

from commands.evennia_overrides.perception import CmdLook


class CommandPayloadTests(TestCase):
    """Tests for :meth:`ArxCommand.to_payload`."""

    def test_gathers_all_dispatchers(self):
        cmd = CmdLook()
        payload = cmd.to_payload()
        assert payload["key"] == "look"
        assert payload["aliases"] == ["glance", "l", "ls"]
        assert payload["dispatchers"] == [
            {"syntax": "look", "context": "room"},
            {"syntax": "look <target>", "context": "object"},
        ]
        assert len(payload["descriptors"]) == 2

    def test_filters_by_context(self):
        cmd = CmdLook()
        room_payload = cmd.to_payload(context="room")
        assert room_payload["dispatchers"] == [{"syntax": "look", "context": "room"}]
        assert len(room_payload["descriptors"]) == 1
        obj_payload = cmd.to_payload(context="object")
        assert obj_payload["dispatchers"] == [
            {"syntax": "look <target>", "context": "object"}
        ]
        assert len(obj_payload["descriptors"]) == 1
