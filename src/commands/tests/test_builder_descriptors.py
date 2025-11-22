from django.test import TestCase

from commands.evennia_overrides.builder import CmdDig, CmdLink, CmdOpen, CmdUnlink


class BuilderCommandDescriptorTests(TestCase):
    """Ensure builder commands expose frontend descriptors."""

    def test_dig_descriptor(self):
        desc = CmdDig().to_payload()["descriptors"][0]
        assert desc["action"] == "@dig"
        assert desc["prompt"] == "@dig room_name=exit_name, back_exit"
        assert "room_name" in desc["params_schema"]

    def test_open_descriptor(self):
        desc = CmdOpen().to_payload()["descriptors"][0]
        assert desc["action"] == "@open"
        assert desc["prompt"] == "@open exit_name=destination"
        assert "destination" in desc["params_schema"]

    def test_link_descriptor(self):
        desc = CmdLink().to_payload()["descriptors"][0]
        assert desc["action"] == "@link"
        assert "exit_name" in desc["params_schema"]

    def test_unlink_descriptor(self):
        desc = CmdUnlink().to_payload()["descriptors"][0]
        assert desc["action"] == "unlink"
        assert desc["prompt"] == "unlink exit_name"
