from django.test import TestCase

from commands.evennia_overrides.builder import CmdDig, CmdLink, CmdOpen, CmdUnlink


class BuilderCommandDescriptorTests(TestCase):
    """Ensure builder commands expose frontend descriptors."""

    def test_dig_descriptor(self):
        desc = CmdDig().to_payload()["descriptors"][0]
        self.assertEqual(desc["action"], "@dig")
        self.assertEqual(desc["prompt"], "@dig room_name=exit_name, back_exit")
        self.assertIn("room_name", desc["params_schema"])

    def test_open_descriptor(self):
        desc = CmdOpen().to_payload()["descriptors"][0]
        self.assertEqual(desc["action"], "@open")
        self.assertEqual(desc["prompt"], "@open exit_name=destination")
        self.assertIn("destination", desc["params_schema"])

    def test_link_descriptor(self):
        desc = CmdLink().to_payload()["descriptors"][0]
        self.assertEqual(desc["action"], "@link")
        self.assertIn("exit_name", desc["params_schema"])

    def test_unlink_descriptor(self):
        desc = CmdUnlink().to_payload()["descriptors"][0]
        self.assertEqual(desc["action"], "unlink")
        self.assertEqual(desc["prompt"], "unlink exit_name")
