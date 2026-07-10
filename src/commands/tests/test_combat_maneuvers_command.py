"""Unit tests for CmdCombat — the ``combat <subverb>`` namespace (#1453, #1452).

Verify subverb routing, REGISTRY ref construction, name-argument resolution, and
the bare-``combat`` status hub, mirroring the mock-caller style of
``test_combat_commands.py``.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.constants import ActionBackend
from actions.types import ActionResult, DispatchResult
from commands.combat_maneuvers import CmdCombat
from commands.exceptions import CommandError

_DISPATCH = "commands.command.dispatch_player_action"


def _make_cmd(args: str) -> CmdCombat:
    cmd = CmdCombat()
    cmd.caller = MagicMock()
    cmd.args = args
    cmd.raw_string = f"combat {args}"
    cmd.cmdname = "combat"
    return cmd


class CmdCombatRoutingTests(TestCase):
    def test_flee_builds_registry_ref(self) -> None:
        cmd = _make_cmd("flee")
        cmd._subverb = "flee"
        ref = cmd.resolve_action_ref()
        self.assertEqual(ref.backend, ActionBackend.REGISTRY)
        self.assertEqual(ref.registry_key, "combat_flee")

    def test_yield_reuses_existing_yield_action(self) -> None:
        cmd = _make_cmd("yield")
        cmd._subverb = "yield"
        ref = cmd.resolve_action_ref()
        self.assertEqual(ref.registry_key, "yield")

    def test_use_builds_registry_ref(self) -> None:
        cmd = _make_cmd("use potion")
        cmd._subverb = "use"
        ref = cmd.resolve_action_ref()
        self.assertEqual(ref.backend, ActionBackend.REGISTRY)
        self.assertEqual(ref.registry_key, "combat_use")

    def test_unknown_subverb_messages_and_does_not_dispatch(self) -> None:
        cmd = _make_cmd("frobnicate")
        with patch(_DISPATCH) as dispatch:
            cmd.func()
        dispatch.assert_not_called()
        cmd.caller.msg.assert_called()

    def test_flee_dispatches_registry_ref_through_func(self) -> None:
        cmd = _make_cmd("flee")
        result = DispatchResult(
            backend=ActionBackend.REGISTRY,
            deferred=False,
            detail=ActionResult(success=True, message="You flee."),
        )
        with patch(_DISPATCH, return_value=result) as dispatch:
            cmd.func()
        dispatch.assert_called_once()
        _, ref, kwargs = dispatch.call_args.args
        self.assertEqual(ref.registry_key, "combat_flee")
        self.assertEqual(kwargs, {})

    def test_bare_combat_shows_status_hub(self) -> None:
        cmd = _make_cmd("")
        with (
            patch.object(cmd, "_combat_participant_or_none", return_value=None) as participant,
            patch.object(cmd, "_render_resource_state", return_value=[]) as resources,
        ):
            cmd.func()
        # Outside combat the hub calls the resource readout collaborator with
        # no participant/action and still prints the actions header.
        participant.assert_called_once()
        resources.assert_called_once_with(None, None)
        cmd.caller.msg.assert_called_once()
        self.assertIn("Combat actions", cmd.caller.msg.call_args.args[0])


class CmdCombatArgResolutionTests(TestCase):
    def test_cover_resolves_ally_kwarg(self) -> None:
        cmd = _make_cmd("cover Bob")
        cmd._subverb, cmd._rest = "cover", "Bob"
        with patch.object(cmd, "_resolve_ally_pk", return_value=5):
            kwargs = cmd.resolve_action_args()
        self.assertEqual(kwargs, {"ally_participant_id": 5})

    def test_cover_without_ally_raises(self) -> None:
        cmd = _make_cmd("cover")
        cmd._subverb, cmd._rest = "cover", ""
        with self.assertRaises(CommandError):
            cmd.resolve_action_args()

    def test_interpose_without_ally_passes_none(self) -> None:
        cmd = _make_cmd("interpose")
        cmd._subverb, cmd._rest = "interpose", ""
        self.assertEqual(cmd.resolve_action_args(), {"ally_participant_id": None})

    def test_combo_resolves_combo_kwarg(self) -> None:
        cmd = _make_cmd("combo Whirlwind")
        cmd._subverb, cmd._rest = "combo", "Whirlwind"
        with patch.object(cmd, "_resolve_combo_pk", return_value=3):
            kwargs = cmd.resolve_action_args()
        self.assertEqual(kwargs, {"combo_id": 3})

    def test_flee_takes_no_args(self) -> None:
        cmd = _make_cmd("flee")
        cmd._subverb, cmd._rest = "flee", ""
        self.assertEqual(cmd.resolve_action_args(), {})

    def test_use_item_only_resolves_item_name(self) -> None:
        cmd = _make_cmd("use healing draught")
        cmd._subverb, cmd._rest = "use", "healing draught"
        self.assertEqual(cmd.resolve_action_args(), {"item_name": "healing draught"})

    def test_use_item_on_ally_resolves_target_kwarg(self) -> None:
        cmd = _make_cmd("use potion on Bob")
        cmd._subverb, cmd._rest = "use", "potion on Bob"
        with patch.object(
            cmd, "_resolve_use_item_target", return_value={"ally_participant_id": 5}
        ) as resolve_target:
            kwargs = cmd.resolve_action_args()
        resolve_target.assert_called_once_with("Bob")
        self.assertEqual(kwargs, {"item_name": "potion", "ally_participant_id": 5})

    def test_use_without_item_raises(self) -> None:
        cmd = _make_cmd("use")
        cmd._subverb, cmd._rest = "use", ""
        with self.assertRaises(CommandError):
            cmd.resolve_action_args()
