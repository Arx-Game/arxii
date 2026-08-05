"""Telnet routing tests for `gm trap` (#3002).

DbHolder trap: Evennia ObjectDB fixtures live in setUp, never setUpTestData.
Behavior lives at the action seam (actions/tests/test_trap_gm_actions.py); these
tests prove the command parses and dispatches, nothing more.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.types import ActionResult
from commands.gm_ops import CmdGMDashboard


def _make_cmd(caller, args: str) -> CmdGMDashboard:
    """Build a CmdGMDashboard with the given caller and args."""
    cmd = CmdGMDashboard()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"gm {args}".strip()
    return cmd


def _messages(caller: MagicMock) -> list[str]:
    """Return all positional string messages sent to *caller*.msg."""
    return [str(c.args[0]) for c in caller.msg.call_args_list if c.args]


class CmdGMTrapTests(TestCase):
    """Each `gm trap` subverb routes to the correct action with the expected kwargs."""

    def setUp(self) -> None:
        self.caller = MagicMock()
        self.caller.msg = MagicMock()

    def _run(self, args: str) -> list[str]:
        cmd = _make_cmd(self.caller, args)
        cmd.func()
        return _messages(self.caller)

    @patch("actions.definitions.traps.ListRoomTrapsAction.run")
    def test_list_dispatches_with_no_extra_kwargs(self, mock_run: MagicMock) -> None:
        mock_run.return_value = ActionResult(success=True, message="No traps here.")
        messages = self._run("trap list")
        mock_run.assert_called_once()
        kwargs = mock_run.call_args.kwargs
        self.assertEqual(kwargs, {"actor": self.caller})
        self.assertIn("No traps here.", messages)

    @patch("actions.definitions.traps.ArmTrapAction.run")
    def test_arm_dispatches_with_trap_id(self, mock_run: MagicMock) -> None:
        mock_run.return_value = ActionResult(success=True, message="Trap armed.")
        messages = self._run("trap arm 7")
        mock_run.assert_called_once()
        kwargs = mock_run.call_args.kwargs
        self.assertEqual(kwargs, {"actor": self.caller, "trap_id": 7})
        self.assertIn("Trap armed.", messages)

    @patch("actions.definitions.traps.GmDisarmTrapAction.run")
    def test_disarm_dispatches_with_trap_id(self, mock_run: MagicMock) -> None:
        mock_run.return_value = ActionResult(success=True, message="Trap disarmed.")
        messages = self._run("trap disarm 7")
        mock_run.assert_called_once()
        kwargs = mock_run.call_args.kwargs
        self.assertEqual(kwargs, {"actor": self.caller, "trap_id": 7})
        self.assertIn("Trap disarmed.", messages)

    @patch("actions.definitions.traps.ArmTrapAction.run")
    def test_arm_without_id_shows_usage_and_dispatches_nothing(self, mock_run: MagicMock) -> None:
        messages = self._run("trap arm")
        mock_run.assert_not_called()
        self.assertTrue(any("Usage: gm trap" in m for m in messages))

    @patch("actions.definitions.traps.ArmTrapAction.run")
    def test_arm_with_non_numeric_id_shows_usage_and_dispatches_nothing(
        self, mock_run: MagicMock
    ) -> None:
        messages = self._run("trap arm banana")
        mock_run.assert_not_called()
        self.assertTrue(any("Usage: gm trap" in m for m in messages))


class CmdGMTrapCmdsetRegistrationTests(TestCase):
    def test_gm_command_still_registered(self) -> None:
        from commands.default_cmdsets import CharacterCmdSet

        cmdset = CharacterCmdSet()
        cmdset.at_cmdset_creation()
        keys = {c.key for c in cmdset.commands}
        self.assertIn("gm", keys)
