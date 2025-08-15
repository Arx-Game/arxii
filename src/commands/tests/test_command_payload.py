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
        self.assertEqual(len(payload["descriptors"]), 2)

    def test_filters_by_context(self):
        cmd = CmdLook()
        room_payload = cmd.to_payload(context="room")
        self.assertEqual(
            room_payload["dispatchers"], [{"syntax": "look", "context": "room"}]
        )
        self.assertEqual(len(room_payload["descriptors"]), 1)
        obj_payload = cmd.to_payload(context="object")
        self.assertEqual(
            obj_payload["dispatchers"],
            [{"syntax": "look <target>", "context": "object"}],
        )
        self.assertEqual(len(obj_payload["descriptors"]), 1)
