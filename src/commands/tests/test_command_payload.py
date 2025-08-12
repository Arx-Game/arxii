from django.test import TestCase

from commands.evennia_overrides.perception import CmdLook


class CommandPayloadTests(TestCase):
    """Tests for :meth:`ArxCommand.to_payload`."""

    def test_gathers_all_dispatchers(self):
        cmd = CmdLook()
        payload = cmd.to_payload()
        self.assertEqual(payload["key"], "look")
        self.assertEqual(payload["aliases"], ["glance", "l", "ls"])
        self.assertEqual(
            payload["dispatchers"],
            [
                {"syntax": "look", "context": "room"},
                {"syntax": "look <target>", "context": "object"},
            ],
        )

    def test_filters_by_context(self):
        cmd = CmdLook()
        room_payload = cmd.to_payload(context="room")
        self.assertEqual(
            room_payload["dispatchers"], [{"syntax": "look", "context": "room"}]
        )
        obj_payload = cmd.to_payload(context="object")
        self.assertEqual(
            obj_payload["dispatchers"],
            [{"syntax": "look <target>", "context": "object"}],
        )
