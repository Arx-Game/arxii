"""Unit tests for CmdDuel — the ``duel <subverb>`` namespace (#1492).

Verify subverb → REGISTRY-key routing, challenge target resolution, optional
challenge-id parsing, the unknown-subverb guard, and the bare-``duel`` status hub.
Mirrors the mock-caller style of ``test_combat_maneuvers_command.py``.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.constants import ActionBackend
from actions.types import ActionResult, DispatchResult
from commands.duels import CmdDuel
from commands.exceptions import CommandError

_DISPATCH = "commands.command.dispatch_player_action"


def _make_cmd(args: str) -> CmdDuel:
    cmd = CmdDuel()
    cmd.caller = MagicMock()
    cmd.args = args
    cmd.raw_string = f"duel {args}"
    cmd.cmdname = "duel"
    return cmd


class CmdDuelRoutingTests(TestCase):
    def test_challenge_builds_registry_ref(self) -> None:
        cmd = _make_cmd("challenge Bob")
        cmd._subverb = "challenge"
        ref = cmd.resolve_action_ref()
        self.assertEqual(ref.backend, ActionBackend.REGISTRY)
        self.assertEqual(ref.registry_key, "challenge")

    def test_accept_builds_registry_ref(self) -> None:
        cmd = _make_cmd("accept")
        cmd._subverb = "accept"
        self.assertEqual(cmd.resolve_action_ref().registry_key, "accept")

    def test_decline_builds_registry_ref(self) -> None:
        cmd = _make_cmd("decline")
        cmd._subverb = "decline"
        self.assertEqual(cmd.resolve_action_ref().registry_key, "decline")

    def test_withdraw_builds_registry_ref(self) -> None:
        cmd = _make_cmd("withdraw")
        cmd._subverb = "withdraw"
        self.assertEqual(cmd.resolve_action_ref().registry_key, "withdraw")

    def test_risk_maps_to_acknowledge_risk_key(self) -> None:
        cmd = _make_cmd("risk")
        cmd._subverb = "risk"
        self.assertEqual(cmd.resolve_action_ref().registry_key, "acknowledge_risk")

    def test_unknown_subverb_messages_and_does_not_dispatch(self) -> None:
        cmd = _make_cmd("frobnicate")
        with patch(_DISPATCH) as dispatch:
            cmd.func()
        dispatch.assert_not_called()
        cmd.caller.msg.assert_called()

    def test_challenge_dispatches_registry_ref_through_func(self) -> None:
        cmd = _make_cmd("challenge Bob")
        cmd.caller.search.return_value = MagicMock()
        result = DispatchResult(
            backend=ActionBackend.REGISTRY,
            deferred=False,
            detail=ActionResult(success=True, message="You issue a duel challenge to Bob."),
        )
        with patch(_DISPATCH, return_value=result) as dispatch:
            cmd.func()
        dispatch.assert_called_once()
        _, ref, _kwargs = dispatch.call_args.args
        self.assertEqual(ref.registry_key, "challenge")

    def test_bare_duel_shows_status_hub(self) -> None:
        cmd = _make_cmd("")
        with (
            patch.object(cmd, "_incoming_challenge", return_value=None),
            patch.object(cmd, "_outgoing_challenge", return_value=None),
            patch.object(cmd, "_active_duel", return_value=None),
            patch(_DISPATCH) as dispatch,
        ):
            cmd.func()
        dispatch.assert_not_called()
        cmd.caller.msg.assert_called_once()
        self.assertIn("Duel actions", cmd.caller.msg.call_args.args[0])


class CmdDuelArgResolutionTests(TestCase):
    def test_challenge_resolves_target_kwarg(self) -> None:
        cmd = _make_cmd("challenge Bob")
        cmd._subverb, cmd._rest = "challenge", "Bob"
        sentinel = MagicMock()
        cmd.caller.search.return_value = sentinel
        kwargs = cmd.resolve_action_args()
        self.assertEqual(kwargs, {"target": sentinel})

    def test_challenge_without_name_raises(self) -> None:
        cmd = _make_cmd("challenge")
        cmd._subverb, cmd._rest = "challenge", ""
        with self.assertRaises(CommandError):
            cmd.resolve_action_args()

    def test_accept_parses_optional_challenge_id(self) -> None:
        cmd = _make_cmd("accept 7")
        cmd._subverb, cmd._rest = "accept", "7"
        self.assertEqual(cmd.resolve_action_args(), {"challenge_id": 7})

    def test_accept_without_id_passes_no_kwargs(self) -> None:
        cmd = _make_cmd("accept")
        cmd._subverb, cmd._rest = "accept", ""
        self.assertEqual(cmd.resolve_action_args(), {})

    def test_decline_parses_optional_challenge_id(self) -> None:
        cmd = _make_cmd("decline 4")
        cmd._subverb, cmd._rest = "decline", "4"
        self.assertEqual(cmd.resolve_action_args(), {"challenge_id": 4})

    def test_withdraw_parses_optional_challenge_id(self) -> None:
        cmd = _make_cmd("withdraw 9")
        cmd._subverb, cmd._rest = "withdraw", "9"
        self.assertEqual(cmd.resolve_action_args(), {"challenge_id": 9})

    def test_non_numeric_challenge_id_raises(self) -> None:
        cmd = _make_cmd("accept bogus")
        cmd._subverb, cmd._rest = "accept", "bogus"
        with self.assertRaises(CommandError):
            cmd.resolve_action_args()

    def test_risk_takes_no_args(self) -> None:
        cmd = _make_cmd("risk")
        cmd._subverb, cmd._rest = "risk", ""
        self.assertEqual(cmd.resolve_action_args(), {})
