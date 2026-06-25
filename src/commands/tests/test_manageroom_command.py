"""manageroom command (#1470) — switch parsing into RoomEditAction kwargs."""

from django.test import TestCase

from commands.exceptions import CommandError
from commands.locations import CmdManageRoom


class ManageRoomParseTests(TestCase):
    def _parse(self, switches: list[str], args: str) -> dict:
        cmd = CmdManageRoom()
        cmd.switches = switches
        cmd.args = args
        return cmd.resolve_action_args()

    def test_name_switch_trims_and_returns_name(self) -> None:
        assert self._parse(["name"], "  The Solar  ") == {"name": "The Solar"}

    def test_desc_switch_returns_description(self) -> None:
        assert self._parse(["desc"], "Warm light, worn rugs.") == {
            "description": "Warm light, worn rugs."
        }

    def test_public_yes_is_true(self) -> None:
        assert self._parse(["public"], "yes") == {"is_public": True}

    def test_public_no_is_false(self) -> None:
        assert self._parse(["public"], "no") == {"is_public": False}

    def test_no_switch_raises_usage(self) -> None:
        with self.assertRaises(CommandError):
            self._parse([], "anything")

    def test_name_requires_a_value(self) -> None:
        with self.assertRaises(CommandError):
            self._parse(["name"], "")
