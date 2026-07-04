"""Unit tests for CmdShip — the ``ship <subverb>`` namespace (#1832 Task 9).

Covers: subverb-map completeness, required-arg missing error paths,
name→instance resolution (ShipType/Covenant) before dispatch, and
resolved-kwargs assertions for commission/upgrade/repair/status (with mocked
dispatch). Mirrors the mock-caller style of ``test_sanctum_command.py`` /
``test_crafting_station.py``.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.constants import ActionBackend
from actions.types import ActionResult, DispatchResult
from commands.exceptions import CommandError
from commands.ships import _SUBVERBS, CmdShip

_DISPATCH = "commands.command.dispatch_player_action"
_SHIP_TYPE_OBJECTS = "world.ships.models.ShipType.objects"
_COVENANT_OBJECTS = "world.covenants.models.Covenant.objects"
_SHIP_DETAILS_OBJECTS = "world.ships.models.ShipDetails.objects"


def _make_cmd(args: str) -> CmdShip:
    cmd = CmdShip()
    cmd.caller = MagicMock()
    cmd.caller.location = MagicMock()
    cmd.args = args
    cmd.raw_string = f"ship {args}"
    cmd.cmdname = "ship"
    return cmd


class ShipCommandParsingTests(TestCase):
    def test_subverb_map_covers_four_ops(self) -> None:
        self.assertEqual(
            set(_SUBVERBS),
            {"commission", "upgrade", "repair", "status"},
        )
        self.assertEqual(_SUBVERBS["commission"], "commission_ship")
        self.assertEqual(_SUBVERBS["upgrade"], "upgrade_ship")
        self.assertEqual(_SUBVERBS["repair"], "repair_ship")
        self.assertEqual(_SUBVERBS["status"], "ship_status")

    def test_unknown_subverb_messages_and_does_not_dispatch(self) -> None:
        cmd = _make_cmd("frobnicate")
        with patch(_DISPATCH) as dispatch:
            cmd.func()
        dispatch.assert_not_called()
        cmd.caller.msg.assert_called()

    def test_bare_ship_shows_status_hub(self) -> None:
        cmd = _make_cmd("")
        with (
            patch(_SHIP_DETAILS_OBJECTS) as sd_obj,
            patch(_DISPATCH) as dispatch,
        ):
            sd_obj.filter.return_value.select_related.return_value.first.return_value = None
            cmd.func()
        dispatch.assert_not_called()
        cmd.caller.msg.assert_called_once()
        self.assertIn("Ship actions", cmd.caller.msg.call_args.args[0])

    def test_bare_status_shows_status_hub(self) -> None:
        cmd = _make_cmd("status")
        with (
            patch(_SHIP_DETAILS_OBJECTS) as sd_obj,
            patch(_DISPATCH) as dispatch,
        ):
            sd_obj.filter.return_value.select_related.return_value.first.return_value = None
            cmd.func()
        dispatch.assert_not_called()


class ShipCommandRefTests(TestCase):
    """resolve_action_ref returns a REGISTRY ActionRef for each subverb."""

    def _cmd_with_subverb(self, subverb: str) -> CmdShip:
        cmd = _make_cmd(subverb)
        cmd._subverb = subverb
        return cmd

    def test_commission_ref(self) -> None:
        cmd = self._cmd_with_subverb("commission")
        ref = cmd.resolve_action_ref()
        self.assertEqual(ref.backend, ActionBackend.REGISTRY)
        self.assertEqual(ref.registry_key, "commission_ship")

    def test_upgrade_ref(self) -> None:
        ref = self._cmd_with_subverb("upgrade").resolve_action_ref()
        self.assertEqual(ref.registry_key, "upgrade_ship")

    def test_repair_ref(self) -> None:
        ref = self._cmd_with_subverb("repair").resolve_action_ref()
        self.assertEqual(ref.registry_key, "repair_ship")

    def test_status_ref(self) -> None:
        ref = self._cmd_with_subverb("status").resolve_action_ref()
        self.assertEqual(ref.registry_key, "ship_status")


class ShipCommandKwargsTests(TestCase):
    """resolve_action_args returns the correct resolved kwargs per subverb."""

    def test_commission_resolves_ship_type_instance(self) -> None:
        cmd = _make_cmd("commission ship_type=Sloop name=Wavecutter")
        cmd._subverb = "commission"
        cmd._rest = "ship_type=Sloop name=Wavecutter"

        mock_ship_type = MagicMock()
        with patch(_SHIP_TYPE_OBJECTS) as st_obj:
            st_obj.filter.return_value.first.return_value = mock_ship_type
            kwargs = cmd.resolve_action_args()

        st_obj.filter.assert_called_once_with(name__iexact="Sloop")
        self.assertEqual(kwargs["ship_type"], mock_ship_type)
        self.assertEqual(kwargs["name"], "Wavecutter")
        self.assertNotIn("covenant", kwargs)

    def test_commission_resolves_covenant_instance(self) -> None:
        cmd = _make_cmd("commission ship_type=Sloop name=Wavecutter covenant=TheTide")
        cmd._subverb = "commission"
        cmd._rest = "ship_type=Sloop name=Wavecutter covenant=TheTide"

        mock_ship_type = MagicMock()
        mock_covenant = MagicMock()
        with (
            patch(_SHIP_TYPE_OBJECTS) as st_obj,
            patch(_COVENANT_OBJECTS) as cov_obj,
        ):
            st_obj.filter.return_value.first.return_value = mock_ship_type
            cov_obj.filter.return_value.first.return_value = mock_covenant
            kwargs = cmd.resolve_action_args()

        cov_obj.filter.assert_called_once_with(name__iexact="TheTide")
        self.assertEqual(kwargs["covenant"], mock_covenant)

    def test_commission_unknown_ship_type_raises_friendly_error(self) -> None:
        cmd = _make_cmd("commission ship_type=Nonexistent name=Wavecutter")
        cmd._subverb = "commission"
        cmd._rest = "ship_type=Nonexistent name=Wavecutter"

        with patch(_SHIP_TYPE_OBJECTS) as st_obj:
            st_obj.filter.return_value.first.return_value = None
            with self.assertRaises(CommandError):
                cmd.resolve_action_args()

    def test_commission_unknown_covenant_raises_friendly_error(self) -> None:
        cmd = _make_cmd("commission ship_type=Sloop name=Wavecutter covenant=Nonexistent")
        cmd._subverb = "commission"
        cmd._rest = "ship_type=Sloop name=Wavecutter covenant=Nonexistent"

        with (
            patch(_SHIP_TYPE_OBJECTS) as st_obj,
            patch(_COVENANT_OBJECTS) as cov_obj,
        ):
            st_obj.filter.return_value.first.return_value = MagicMock()
            cov_obj.filter.return_value.first.return_value = None
            with self.assertRaises(CommandError):
                cmd.resolve_action_args()

    def test_commission_missing_name_raises_command_error(self) -> None:
        cmd = _make_cmd("commission ship_type=Sloop")
        cmd._subverb = "commission"
        cmd._rest = "ship_type=Sloop"

        with self.assertRaises(CommandError):
            cmd.resolve_action_args()

    def test_commission_missing_ship_type_raises_command_error(self) -> None:
        cmd = _make_cmd("commission name=Wavecutter")
        cmd._subverb = "commission"
        cmd._rest = "name=Wavecutter"

        with self.assertRaises(CommandError):
            cmd.resolve_action_args()

    def test_upgrade_resolves_stat_and_target_level(self) -> None:
        cmd = _make_cmd("upgrade stat=handling level=3")
        cmd._subverb = "upgrade"
        cmd._rest = "stat=handling level=3"

        kwargs = cmd.resolve_action_args()

        self.assertEqual(kwargs["stat"], "handling")
        self.assertEqual(kwargs["target_level"], 3)
        self.assertNotIn("ship_id", kwargs)

    def test_upgrade_resolves_optional_ship_id(self) -> None:
        cmd = _make_cmd("upgrade stat=handling level=3 ship_id=7")
        cmd._subverb = "upgrade"
        cmd._rest = "stat=handling level=3 ship_id=7"

        kwargs = cmd.resolve_action_args()

        self.assertEqual(kwargs["ship_id"], 7)

    def test_upgrade_missing_level_raises_command_error(self) -> None:
        cmd = _make_cmd("upgrade stat=handling")
        cmd._subverb = "upgrade"
        cmd._rest = "stat=handling"

        with self.assertRaises(CommandError):
            cmd.resolve_action_args()

    def test_upgrade_missing_stat_raises_command_error(self) -> None:
        cmd = _make_cmd("upgrade level=3")
        cmd._subverb = "upgrade"
        cmd._rest = "level=3"

        with self.assertRaises(CommandError):
            cmd.resolve_action_args()

    def test_repair_no_args_returns_empty_kwargs(self) -> None:
        cmd = _make_cmd("repair")
        cmd._subverb = "repair"
        cmd._rest = ""

        kwargs = cmd.resolve_action_args()

        self.assertEqual(kwargs, {})

    def test_repair_resolves_optional_ship_id(self) -> None:
        cmd = _make_cmd("repair ship_id=4")
        cmd._subverb = "repair"
        cmd._rest = "ship_id=4"

        kwargs = cmd.resolve_action_args()

        self.assertEqual(kwargs, {"ship_id": 4})

    def test_status_resolves_optional_ship_id(self) -> None:
        cmd = _make_cmd("status ship_id=9")
        cmd._subverb = "status"
        cmd._rest = "ship_id=9"

        kwargs = cmd.resolve_action_args()

        self.assertEqual(kwargs, {"ship_id": 9})


class ShipCommandDispatchTests(TestCase):
    """Full func() dispatch tests — mock dispatch_player_action to assert kwargs."""

    def test_upgrade_dispatches_with_resolved_kwargs(self) -> None:
        cmd = _make_cmd("upgrade stat=handling level=3")
        result = DispatchResult(
            backend=ActionBackend.REGISTRY,
            deferred=False,
            detail=ActionResult(success=True, message="Upgrade begins."),
        )
        with patch(_DISPATCH, return_value=result) as dispatch:
            cmd.func()

        dispatch.assert_called_once()
        _, ref, kwargs = dispatch.call_args.args
        self.assertEqual(ref.registry_key, "upgrade_ship")
        self.assertEqual(kwargs["stat"], "handling")
        self.assertEqual(kwargs["target_level"], 3)

    def test_commission_dispatches_with_resolved_ship_type(self) -> None:
        cmd = _make_cmd("commission ship_type=Sloop name=Wavecutter")
        mock_ship_type = MagicMock()
        result = DispatchResult(
            backend=ActionBackend.REGISTRY,
            deferred=False,
            detail=ActionResult(success=True, message="Construction commissioned."),
        )
        with (
            patch(_SHIP_TYPE_OBJECTS) as st_obj,
            patch(_DISPATCH, return_value=result) as dispatch,
        ):
            st_obj.filter.return_value.first.return_value = mock_ship_type
            cmd.func()

        dispatch.assert_called_once()
        _, ref, kwargs = dispatch.call_args.args
        self.assertEqual(ref.registry_key, "commission_ship")
        self.assertEqual(kwargs["ship_type"], mock_ship_type)
        self.assertEqual(kwargs["name"], "Wavecutter")

    def test_commission_unknown_ship_type_does_not_dispatch(self) -> None:
        cmd = _make_cmd("commission ship_type=Nonexistent name=Wavecutter")
        with (
            patch(_SHIP_TYPE_OBJECTS) as st_obj,
            patch(_DISPATCH) as dispatch,
        ):
            st_obj.filter.return_value.first.return_value = None
            cmd.func()

        dispatch.assert_not_called()
        cmd.caller.msg.assert_called()

    def test_repair_dispatches_through_func(self) -> None:
        cmd = _make_cmd("repair ship_id=4")
        result = DispatchResult(
            backend=ActionBackend.REGISTRY,
            deferred=False,
            detail=ActionResult(success=True, message="Repairs begin."),
        )
        with patch(_DISPATCH, return_value=result) as dispatch:
            cmd.func()

        dispatch.assert_called_once()
        _, ref, kwargs = dispatch.call_args.args
        self.assertEqual(ref.registry_key, "repair_ship")
        self.assertEqual(kwargs["ship_id"], 4)

    def test_status_with_ship_id_dispatches_through_func(self) -> None:
        cmd = _make_cmd("status ship_id=9")
        result = DispatchResult(
            backend=ActionBackend.REGISTRY,
            deferred=False,
            detail=ActionResult(success=True, message="ship: hull 10."),
        )
        with patch(_DISPATCH, return_value=result) as dispatch:
            cmd.func()

        dispatch.assert_called_once()
        _, ref, kwargs = dispatch.call_args.args
        self.assertEqual(ref.registry_key, "ship_status")
        self.assertEqual(kwargs["ship_id"], 9)
