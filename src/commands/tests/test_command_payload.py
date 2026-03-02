"""Tests for ArxCommand.to_payload()."""

from django.test import TestCase

from commands.evennia_overrides.perception import CmdLook


class CommandPayloadTests(TestCase):
    def test_look_payload_uses_action_metadata(self):
        cmd = CmdLook()
        payload = cmd.to_payload()
        assert payload["key"] == "look"
        assert payload["aliases"] == ["glance", "l", "ls"]
        assert len(payload["descriptors"]) == 1
        desc = payload["descriptors"][0]
        assert desc["action"] == "look"
        assert desc["icon"] == "eye"
