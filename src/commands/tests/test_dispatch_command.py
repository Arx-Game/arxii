"""Tests for the DispatchCommand telnet base (rides dispatch_player_action)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.constants import ActionBackend
from actions.errors import ActionDispatchError
from actions.types import ActionRef, DispatchResult
from commands.command import DispatchCommand


class _ProbeDispatchCommand(DispatchCommand):
    key = "probe"

    def resolve_action_ref(self) -> ActionRef:
        return ActionRef(backend=ActionBackend.REGISTRY, registry_key="probe")

    def resolve_action_args(self) -> dict:
        return {"foo": "bar"}


def _make_cmd(cls, caller, args=""):
    cmd = cls()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"{cmd.key} {args}"
    cmd.cmdname = cmd.key
    return cmd


class DispatchCommandTests(TestCase):
    def setUp(self) -> None:
        self.caller = MagicMock()

    def test_func_calls_dispatcher_with_ref_and_kwargs(self) -> None:
        cmd = _make_cmd(_ProbeDispatchCommand, self.caller)
        with patch("commands.command.dispatch_player_action") as mock_dispatch:
            mock_dispatch.return_value = DispatchResult(
                backend=ActionBackend.REGISTRY, deferred=True
            )
            cmd.func()
        ref = mock_dispatch.call_args.args[1]
        kwargs = mock_dispatch.call_args.args[2]
        self.assertEqual(ref.backend, ActionBackend.REGISTRY)
        self.assertEqual(kwargs, {"foo": "bar"})

    def test_deferred_result_reports_to_caller(self) -> None:
        cmd = _make_cmd(_ProbeDispatchCommand, self.caller)
        with patch("commands.command.dispatch_player_action") as mock_dispatch:
            mock_dispatch.return_value = DispatchResult(backend=ActionBackend.COMBAT, deferred=True)
            cmd.func()
        self.caller.msg.assert_called()

    def test_dispatch_error_shows_user_message(self) -> None:
        cmd = _make_cmd(_ProbeDispatchCommand, self.caller)
        with patch("commands.command.dispatch_player_action") as mock_dispatch:
            mock_dispatch.side_effect = ActionDispatchError(ActionDispatchError.UNKNOWN_ACTION_REF)
            cmd.func()
        self.caller.msg.assert_called_with("That action is no longer available.")
