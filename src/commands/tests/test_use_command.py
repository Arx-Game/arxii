"""Tests for CmdUse command parsing."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.definitions.items import UseItemAction
from actions.types import ActionResult
from commands.evennia_overrides.items import CmdUse
from commands.exceptions import CommandError
from evennia_extensions.factories import ObjectDBFactory


def _make_cmd(cls, caller, args=""):
    """Create a command instance with caller and args set."""
    cmd = cls()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"{cmd.key} {args}"
    cmd.obj = None
    cmd.cmdname = cmd.key
    return cmd


class CmdUseTests(TestCase):
    def setUp(self):
        self.room = ObjectDBFactory(
            db_key="UseRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.caller = ObjectDBFactory(
            db_key="UseAlice",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        self.item = ObjectDBFactory(db_key="Potion", location=self.caller)
        self.target = ObjectDBFactory(db_key="Bob", location=self.room)
        self.caller.msg = MagicMock()

    def test_use_item_only(self):
        """'use <item>' resolves item and leaves target as None."""
        self.caller.search = MagicMock(return_value=self.item)
        cmd = _make_cmd(CmdUse, self.caller, args=" Potion")
        result = cmd.resolve_action_args()
        self.assertEqual(result, {"item": self.item, "target": None})
        self.caller.search.assert_called_once_with("Potion")

    def test_use_item_on_target(self):
        """'use <item> on <target>' resolves both item and target."""
        self.caller.search = MagicMock(side_effect=[self.item, self.target])
        cmd = _make_cmd(CmdUse, self.caller, args=" Potion on Bob")
        result = cmd.resolve_action_args()
        self.assertEqual(result, {"item": self.item, "target": self.target})
        self.assertEqual(self.caller.search.call_count, 2)

    def test_use_empty_args_raises_command_error(self):
        """Empty args raises CommandError."""
        cmd = _make_cmd(CmdUse, self.caller, args="")
        with self.assertRaises(CommandError):
            cmd.resolve_action_args()

    def test_use_action_is_use_item_action(self):
        """CmdUse.action is a UseItemAction instance."""
        cmd = CmdUse()
        self.assertIsInstance(cmd.action, UseItemAction)

    def test_use_delegates_to_action(self):
        """func() calls action.run with resolved item and target=None."""
        self.caller.search = MagicMock(return_value=self.item)
        cmd = _make_cmd(CmdUse, self.caller, args=" Potion")
        with patch.object(cmd.action, "run", return_value=ActionResult(success=True)) as mock_run:
            cmd.func()
            mock_run.assert_called_once_with(actor=self.caller, item=self.item, target=None)
