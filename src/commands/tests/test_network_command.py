"""Routing tests for the ``network`` telnet command family (#2820)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.types import ActionResult
from commands.network import CmdNetwork


def _make_cmd(caller, args: str) -> CmdNetwork:
    cmd = CmdNetwork()
    cmd.caller = caller
    cmd.args = args
    cmd.switches = []
    cmd.raw_string = f"network {args}".strip()
    return cmd


def _messages(caller: MagicMock) -> list[str]:
    return [str(c.args[0]) for c in caller.msg.call_args_list if c.args]


class CmdNetworkRoutingTests(TestCase):
    def setUp(self) -> None:
        self.caller = MagicMock()
        self.caller.msg = MagicMock()

    def _run(self, args: str) -> list[str]:
        cmd = _make_cmd(self.caller, args)
        cmd.func()
        return _messages(self.caller)

    def test_unknown_subverb_shows_usage(self) -> None:
        messages = self._run("skulk")
        self.assertTrue(any("Usage" in m for m in messages))

    @patch("actions.registry.get_action")
    def test_bare_network_runs_board(self, get_action) -> None:
        get_action.return_value.run.return_value = ActionResult(success=True, message="board")
        self._run("")
        get_action.assert_called_once_with("list_org_tasks")
        get_action.return_value.run.assert_called_once_with(self.caller)

    @patch("actions.registry.get_action")
    def test_accept_parses_task_id(self, get_action) -> None:
        get_action.return_value.run.return_value = ActionResult(success=True, message="ok")
        self._run("accept 42")
        get_action.assert_called_once_with("accept_org_task")
        get_action.return_value.run.assert_called_once_with(self.caller, task_id=42)

    @patch("actions.registry.get_action")
    def test_sweep_routes_to_detect(self, get_action) -> None:
        get_action.return_value.run.return_value = ActionResult(success=True, message="ok")
        self._run("sweep")
        get_action.assert_called_once_with("detect_listeners")

    @patch.object(CmdNetwork, "_resolve_agent")
    @patch("actions.registry.get_action")
    def test_assign_parses_task_and_agent(self, get_action, resolve_agent) -> None:
        resolve_agent.return_value = MagicMock(pk=7)
        get_action.return_value.run.return_value = ActionResult(success=True, message="ok")
        self._run("assign 42 = Alia the Barkeep")
        resolve_agent.assert_called_once_with("Alia the Barkeep")
        get_action.assert_called_once_with("assign_task_agent")
        get_action.return_value.run.assert_called_once_with(self.caller, task_id=42, npc_asset_id=7)

    def test_accept_rejects_non_numeric(self) -> None:
        messages = self._run("accept soon")
        self.assertTrue(any("Usage" in m for m in messages))
