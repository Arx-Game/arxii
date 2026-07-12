"""Unit tests for CmdDefense — the ``defense <subverb>`` namespace (#2177).

Mirrors ``test_crafting_station.py``'s shape (the byte-exact structural match:
``CmdDefense`` is a ``DispatchCommand`` with the same subverb-routing pattern as
``CmdLabStation``, dispatching through ``dispatch_player_action`` rather than
calling ``Action.run()`` directly — unlike ``CmdPick``/``CmdBreak`` in
``test_door.py``, which are plain ``ArxCommand`` subclasses that patch
``Action.run`` directly). Covers: subverb-map completeness, required-arg
missing error paths, resolved-kwargs assertions for install/upgrade/fund, and
full ``func()`` dispatch with mocked ``dispatch_player_action``.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.constants import ActionBackend
from actions.types import ActionResult, DispatchResult
from commands.defenses import _SUBVERBS, CmdDefense
from commands.exceptions import CommandError

_DISPATCH = "commands.command.dispatch_player_action"
_ROOM_PROFILE_OBJECTS = "evennia_extensions.models.RoomProfile.objects"
_RESONANCE_OBJECTS = "world.magic.models.affinity.Resonance.objects"


def _make_cmd(args: str) -> CmdDefense:
    cmd = CmdDefense()
    cmd.caller = MagicMock()
    cmd.caller.location = MagicMock()
    cmd.args = args
    cmd.raw_string = f"defense {args}"
    cmd.cmdname = "defense"
    return cmd


class DefenseCommandParsingTests(TestCase):
    def test_subverb_map_covers_three_ops(self) -> None:
        self.assertEqual(set(_SUBVERBS), {"install", "upgrade", "fund"})

    def test_unknown_subverb_messages_and_does_not_dispatch(self) -> None:
        cmd = _make_cmd("frobnicate")
        with patch(_DISPATCH) as dispatch:
            cmd.func()
        dispatch.assert_not_called()
        cmd.caller.msg.assert_called()

    def test_bare_defense_shows_status_hub(self) -> None:
        cmd = _make_cmd("")
        with (
            patch(_ROOM_PROFILE_OBJECTS) as rp_obj,
            patch(_DISPATCH) as dispatch,
        ):
            rp_obj.filter.return_value.first.return_value = None
            cmd.func()
        dispatch.assert_not_called()
        cmd.caller.msg.assert_called_once()
        self.assertIn("Defense actions", cmd.caller.msg.call_args.args[0])


class DefenseCommandRefTests(TestCase):
    """resolve_action_ref returns a REGISTRY ActionRef for each subverb."""

    def _cmd_with_subverb(self, subverb: str) -> CmdDefense:
        cmd = _make_cmd(subverb)
        cmd._subverb = subverb
        return cmd

    def test_install_ref(self) -> None:
        cmd = self._cmd_with_subverb("install")
        ref = cmd.resolve_action_ref()
        self.assertEqual(ref.backend, ActionBackend.REGISTRY)
        self.assertEqual(ref.registry_key, "start_defense_installation")

    def test_upgrade_ref(self) -> None:
        ref = self._cmd_with_subverb("upgrade").resolve_action_ref()
        self.assertEqual(ref.registry_key, "start_defense_installation")

    def test_fund_ref(self) -> None:
        ref = self._cmd_with_subverb("fund").resolve_action_ref()
        self.assertEqual(ref.registry_key, "fund_room_ward")


class DefenseCommandKwargsTests(TestCase):
    """resolve_action_args returns the correct resolved kwargs per subverb."""

    def test_install_alarm_defaults_level_to_one(self) -> None:
        cmd = _make_cmd("install alarm")
        cmd._subverb = "install"
        cmd._rest = "alarm"

        kwargs = cmd.resolve_action_args()

        self.assertEqual(kwargs["defense_kind"], "ROOM_ALARM")
        self.assertEqual(kwargs["target_level"], 1)

    def test_install_alarm_explicit_level(self) -> None:
        cmd = _make_cmd("install alarm level=3")
        cmd._subverb = "install"
        cmd._rest = "alarm level=3"

        kwargs = cmd.resolve_action_args()

        self.assertEqual(kwargs["defense_kind"], "ROOM_ALARM")
        self.assertEqual(kwargs["target_level"], 3)

    def test_upgrade_requires_level(self) -> None:
        cmd = _make_cmd("upgrade alarm")
        cmd._subverb = "upgrade"
        cmd._rest = "alarm"

        with self.assertRaises(CommandError):
            cmd.resolve_action_args()

    def test_upgrade_resolves_level(self) -> None:
        cmd = _make_cmd("upgrade alarm level=2")
        cmd._subverb = "upgrade"
        cmd._rest = "alarm level=2"

        kwargs = cmd.resolve_action_args()

        self.assertEqual(kwargs["defense_kind"], "ROOM_ALARM")
        self.assertEqual(kwargs["target_level"], 2)

    def test_install_missing_kind_raises_command_error(self) -> None:
        cmd = _make_cmd("install")
        cmd._subverb = "install"
        cmd._rest = ""

        with self.assertRaises(CommandError):
            cmd.resolve_action_args()

    def test_install_unknown_kind_raises_command_error(self) -> None:
        cmd = _make_cmd("install portcullis")
        cmd._subverb = "install"
        cmd._rest = "portcullis"

        with self.assertRaises(CommandError):
            cmd.resolve_action_args()

    def test_install_bars_resolves_exit(self) -> None:
        cmd = _make_cmd("install bars exit=gate")
        cmd._subverb = "install"
        cmd._rest = "bars exit=gate"
        mock_exit = MagicMock()
        cmd.caller.search.return_value = mock_exit

        kwargs = cmd.resolve_action_args()

        self.assertEqual(kwargs["defense_kind"], "EXIT_BARS")
        self.assertEqual(kwargs["exit"], mock_exit)
        cmd.caller.search.assert_called_once_with("gate", location=cmd.caller.location)

    def test_install_bars_missing_exit_raises_command_error(self) -> None:
        cmd = _make_cmd("install bars")
        cmd._subverb = "install"
        cmd._rest = "bars"
        cmd.caller.search.return_value = None

        with self.assertRaises(CommandError):
            cmd.resolve_action_args()

    def test_install_ward_resolves_resonance(self) -> None:
        cmd = _make_cmd("install ward resonance=Passion")
        cmd._subverb = "install"
        cmd._rest = "ward resonance=Passion"
        mock_resonance = MagicMock()
        with patch(_RESONANCE_OBJECTS) as res_obj:
            res_obj.filter.return_value.first.return_value = mock_resonance
            kwargs = cmd.resolve_action_args()

        self.assertEqual(kwargs["defense_kind"], "ROOM_WARD")
        self.assertEqual(kwargs["resonance"], mock_resonance)

    def test_install_ward_missing_resonance_raises_command_error(self) -> None:
        cmd = _make_cmd("install ward")
        cmd._subverb = "install"
        cmd._rest = "ward"

        with self.assertRaises(CommandError):
            cmd.resolve_action_args()

    def test_install_ward_unknown_resonance_raises_command_error(self) -> None:
        cmd = _make_cmd("install ward resonance=Nonexistent")
        cmd._subverb = "install"
        cmd._rest = "ward resonance=Nonexistent"
        with patch(_RESONANCE_OBJECTS) as res_obj:
            res_obj.filter.return_value.first.return_value = None
            with self.assertRaises(CommandError):
                cmd.resolve_action_args()

    def test_install_ward_resolves_condition_and_damage(self) -> None:
        cmd = _make_cmd("install ward resonance=Fire condition=Burning damage=5")
        cmd._subverb = "install"
        cmd._rest = "ward resonance=Fire condition=Burning damage=5"
        mock_resonance = MagicMock()
        mock_condition = MagicMock()
        mock_condition.category.is_negative = True
        with (
            patch(_RESONANCE_OBJECTS) as res_obj,
            patch("world.conditions.models.ConditionTemplate.objects") as cond_obj,
        ):
            res_obj.filter.return_value.first.return_value = mock_resonance
            cond_obj.filter.return_value.first.return_value = mock_condition
            kwargs = cmd.resolve_action_args()

        self.assertEqual(kwargs["defense_kind"], "ROOM_WARD")
        self.assertEqual(kwargs["resonance"], mock_resonance)
        self.assertEqual(kwargs["reaction_condition"], mock_condition)
        self.assertEqual(kwargs["reaction_damage_amount"], 5)

    def test_install_ward_unknown_condition_raises_command_error(self) -> None:
        cmd = _make_cmd("install ward resonance=Fire condition=Nonexistent")
        cmd._subverb = "install"
        cmd._rest = "ward resonance=Fire condition=Nonexistent"
        mock_resonance = MagicMock()
        with (
            patch(_RESONANCE_OBJECTS) as res_obj,
            patch("world.conditions.models.ConditionTemplate.objects") as cond_obj,
        ):
            res_obj.filter.return_value.first.return_value = mock_resonance
            cond_obj.filter.return_value.first.return_value = None
            with self.assertRaises(CommandError):
                cmd.resolve_action_args()

    def test_install_ward_non_negative_condition_raises_command_error(self) -> None:
        cmd = _make_cmd("install ward resonance=Fire condition=Empowered")
        cmd._subverb = "install"
        cmd._rest = "ward resonance=Fire condition=Empowered"
        mock_resonance = MagicMock()
        mock_condition = MagicMock()
        mock_condition.category.is_negative = False
        with (
            patch(_RESONANCE_OBJECTS) as res_obj,
            patch("world.conditions.models.ConditionTemplate.objects") as cond_obj,
        ):
            res_obj.filter.return_value.first.return_value = mock_resonance
            cond_obj.filter.return_value.first.return_value = mock_condition
            with self.assertRaises(CommandError):
                cmd.resolve_action_args()

    def test_install_ward_damage_only_without_condition(self) -> None:
        cmd = _make_cmd("install ward resonance=Fire damage=10")
        cmd._subverb = "install"
        cmd._rest = "ward resonance=Fire damage=10"
        mock_resonance = MagicMock()
        with patch(_RESONANCE_OBJECTS) as res_obj:
            res_obj.filter.return_value.first.return_value = mock_resonance
            kwargs = cmd.resolve_action_args()

        self.assertEqual(kwargs["defense_kind"], "ROOM_WARD")
        self.assertEqual(kwargs["resonance"], mock_resonance)
        self.assertEqual(kwargs["reaction_damage_amount"], 10)
        self.assertNotIn("reaction_condition", kwargs)

    def test_install_ward_invalid_damage_raises_command_error(self) -> None:
        cmd = _make_cmd("install ward resonance=Fire damage=abc")
        cmd._subverb = "install"
        cmd._rest = "ward resonance=Fire damage=abc"
        mock_resonance = MagicMock()
        with patch(_RESONANCE_OBJECTS) as res_obj:
            res_obj.filter.return_value.first.return_value = mock_resonance
            with self.assertRaises(CommandError):
                cmd.resolve_action_args()

    def test_fund_resolves_amount(self) -> None:
        cmd = _make_cmd("fund amount=50")
        cmd._subverb = "fund"
        cmd._rest = "amount=50"

        kwargs = cmd.resolve_action_args()

        self.assertEqual(kwargs, {"amount": 50})

    def test_fund_missing_amount_raises_command_error(self) -> None:
        cmd = _make_cmd("fund")
        cmd._subverb = "fund"
        cmd._rest = ""

        with self.assertRaises(CommandError):
            cmd.resolve_action_args()


class DefenseCommandDispatchTests(TestCase):
    """Full func() dispatch tests — mock dispatch_player_action to assert kwargs."""

    def test_install_alarm_dispatches_through_func(self) -> None:
        cmd = _make_cmd("install alarm level=1")
        result = DispatchResult(
            backend=ActionBackend.REGISTRY,
            deferred=False,
            detail=ActionResult(success=True, message="A project begins."),
        )
        with patch(_DISPATCH, return_value=result) as dispatch:
            cmd.func()

        dispatch.assert_called_once()
        _, ref, kwargs = dispatch.call_args.args
        self.assertEqual(ref.registry_key, "start_defense_installation")
        self.assertEqual(kwargs["defense_kind"], "ROOM_ALARM")
        self.assertEqual(kwargs["target_level"], 1)

    def test_fund_dispatches_through_func(self) -> None:
        cmd = _make_cmd("fund amount=25")
        result = DispatchResult(
            backend=ActionBackend.REGISTRY,
            deferred=False,
            detail=ActionResult(success=True, message="You feed the ward."),
        )
        with patch(_DISPATCH, return_value=result) as dispatch:
            cmd.func()

        dispatch.assert_called_once()
        _, ref, kwargs = dispatch.call_args.args
        self.assertEqual(ref.registry_key, "fund_room_ward")
        self.assertEqual(kwargs["amount"], 25)
