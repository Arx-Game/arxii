"""Unit tests for CmdLabStation — the ``station <subverb>`` namespace (#1234).

Covers: subverb-map completeness, required-arg missing error paths, and
resolved-kwargs assertions for install / upgrade / repair (with mocked
dispatch). Mirrors the mock-caller style of ``test_sanctum_command.py``.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.constants import ActionBackend
from actions.types import ActionResult, DispatchResult
from commands.crafting_station import _SUBVERBS, CmdLabStation
from commands.exceptions import CommandError

_DISPATCH = "commands.command.dispatch_player_action"
_ROOM_PROFILE_OBJECTS = "evennia_extensions.models.RoomProfile.objects"
_ENSURE_LAB_KIND = "world.room_features.seeds.ensure_lab_kind"


def _make_cmd(args: str) -> CmdLabStation:
    cmd = CmdLabStation()
    cmd.caller = MagicMock()
    cmd.caller.location = MagicMock()
    cmd.args = args
    cmd.raw_string = f"station {args}"
    cmd.cmdname = "station"
    return cmd


class LabStationCommandParsingTests(TestCase):
    def test_subverb_map_covers_three_ops(self) -> None:
        self.assertEqual(set(_SUBVERBS), {"install", "upgrade", "repair"})

    def test_unknown_subverb_messages_and_does_not_dispatch(self) -> None:
        cmd = _make_cmd("frobnicate")
        with patch(_DISPATCH) as dispatch:
            cmd.func()
        dispatch.assert_not_called()
        cmd.caller.msg.assert_called()

    def test_bare_station_shows_status_hub(self) -> None:
        cmd = _make_cmd("")
        with (
            patch(_ROOM_PROFILE_OBJECTS) as rp_obj,
            patch(_DISPATCH) as dispatch,
        ):
            rp_obj.filter.return_value.first.return_value = None
            cmd.func()
        dispatch.assert_not_called()
        cmd.caller.msg.assert_called_once()
        self.assertIn("Station actions", cmd.caller.msg.call_args.args[0])


class LabStationCommandRefTests(TestCase):
    """resolve_action_ref returns a REGISTRY ActionRef for each subverb."""

    def _cmd_with_subverb(self, subverb: str) -> CmdLabStation:
        cmd = _make_cmd(subverb)
        cmd._subverb = subverb
        return cmd

    def test_install_ref(self) -> None:
        cmd = self._cmd_with_subverb("install")
        ref = cmd.resolve_action_ref()
        self.assertEqual(ref.backend, ActionBackend.REGISTRY)
        self.assertEqual(ref.registry_key, "start_room_feature_project")

    def test_upgrade_ref(self) -> None:
        ref = self._cmd_with_subverb("upgrade").resolve_action_ref()
        self.assertEqual(ref.registry_key, "start_room_feature_project")

    def test_repair_ref(self) -> None:
        ref = self._cmd_with_subverb("repair").resolve_action_ref()
        self.assertEqual(ref.registry_key, "repair_lab_station")


class LabStationCommandKwargsTests(TestCase):
    """resolve_action_args returns the correct resolved kwargs per subverb."""

    def test_install_defaults_level_to_one(self) -> None:
        cmd = _make_cmd("install")
        cmd._subverb = "install"
        cmd._rest = ""

        mock_rp = MagicMock()
        mock_kind = MagicMock()
        with (
            patch(_ROOM_PROFILE_OBJECTS) as rp_obj,
            patch(_ENSURE_LAB_KIND, return_value=mock_kind),
        ):
            rp_obj.filter.return_value.first.return_value = mock_rp
            kwargs = cmd.resolve_action_args()

        self.assertEqual(kwargs["room_profile"], mock_rp)
        self.assertEqual(kwargs["feature_kind"], mock_kind)
        self.assertEqual(kwargs["target_level"], 1)

    def test_install_explicit_level(self) -> None:
        cmd = _make_cmd("install level=3")
        cmd._subverb = "install"
        cmd._rest = "level=3"

        mock_rp = MagicMock()
        with (
            patch(_ROOM_PROFILE_OBJECTS) as rp_obj,
            patch(_ENSURE_LAB_KIND),
        ):
            rp_obj.filter.return_value.first.return_value = mock_rp
            kwargs = cmd.resolve_action_args()

        self.assertEqual(kwargs["target_level"], 3)

    def test_upgrade_requires_level(self) -> None:
        cmd = _make_cmd("upgrade")
        cmd._subverb = "upgrade"
        cmd._rest = ""

        mock_rp = MagicMock()
        with (
            patch(_ROOM_PROFILE_OBJECTS) as rp_obj,
            patch(_ENSURE_LAB_KIND),
        ):
            rp_obj.filter.return_value.first.return_value = mock_rp
            with self.assertRaises(CommandError):
                cmd.resolve_action_args()

    def test_upgrade_resolves_level(self) -> None:
        cmd = _make_cmd("upgrade level=2")
        cmd._subverb = "upgrade"
        cmd._rest = "level=2"

        mock_rp = MagicMock()
        with (
            patch(_ROOM_PROFILE_OBJECTS) as rp_obj,
            patch(_ENSURE_LAB_KIND),
        ):
            rp_obj.filter.return_value.first.return_value = mock_rp
            kwargs = cmd.resolve_action_args()

        self.assertEqual(kwargs["target_level"], 2)

    def test_repair_resolves_points(self) -> None:
        cmd = _make_cmd("repair points=50")
        cmd._subverb = "repair"
        cmd._rest = "points=50"

        mock_rp = MagicMock()
        with patch(_ROOM_PROFILE_OBJECTS) as rp_obj:
            rp_obj.filter.return_value.first.return_value = mock_rp
            kwargs = cmd.resolve_action_args()

        self.assertEqual(kwargs["room_profile"], mock_rp)
        self.assertEqual(kwargs["restore_points"], 50)

    def test_repair_missing_points_raises_command_error(self) -> None:
        cmd = _make_cmd("repair")
        cmd._subverb = "repair"
        cmd._rest = ""

        mock_rp = MagicMock()
        with patch(_ROOM_PROFILE_OBJECTS) as rp_obj:
            rp_obj.filter.return_value.first.return_value = mock_rp
            with self.assertRaises(CommandError):
                cmd.resolve_action_args()

    def test_no_room_profile_raises_command_error(self) -> None:
        cmd = _make_cmd("repair points=10")
        cmd._subverb = "repair"
        cmd._rest = "points=10"

        with patch(_ROOM_PROFILE_OBJECTS) as rp_obj:
            rp_obj.filter.return_value.first.return_value = None
            with self.assertRaises(CommandError):
                cmd.resolve_action_args()

    def test_no_location_raises_command_error(self) -> None:
        cmd = _make_cmd("repair points=10")
        cmd._subverb = "repair"
        cmd._rest = "points=10"
        cmd.caller.location = None

        with self.assertRaises(CommandError):
            cmd.resolve_action_args()


class LabStationCommandDispatchTests(TestCase):
    """Full func() dispatch tests — mock dispatch_player_action to assert kwargs."""

    def test_install_dispatches_through_func(self) -> None:
        cmd = _make_cmd("install level=1")
        mock_rp = MagicMock()
        result = DispatchResult(
            backend=ActionBackend.REGISTRY,
            deferred=False,
            detail=ActionResult(success=True, message="A project begins."),
        )
        with (
            patch(_ROOM_PROFILE_OBJECTS) as rp_obj,
            patch(_ENSURE_LAB_KIND),
            patch(_DISPATCH, return_value=result) as dispatch,
        ):
            rp_obj.filter.return_value.first.return_value = mock_rp
            cmd.func()

        dispatch.assert_called_once()
        _, ref, kwargs = dispatch.call_args.args
        self.assertEqual(ref.registry_key, "start_room_feature_project")
        self.assertEqual(kwargs["room_profile"], mock_rp)
        self.assertEqual(kwargs["target_level"], 1)

    def test_upgrade_dispatches_through_func(self) -> None:
        cmd = _make_cmd("upgrade level=2")
        mock_rp = MagicMock()
        result = DispatchResult(
            backend=ActionBackend.REGISTRY,
            deferred=False,
            detail=ActionResult(success=True, message="A project begins."),
        )
        with (
            patch(_ROOM_PROFILE_OBJECTS) as rp_obj,
            patch(_ENSURE_LAB_KIND),
            patch(_DISPATCH, return_value=result) as dispatch,
        ):
            rp_obj.filter.return_value.first.return_value = mock_rp
            cmd.func()

        dispatch.assert_called_once()
        _, ref, kwargs = dispatch.call_args.args
        self.assertEqual(ref.registry_key, "start_room_feature_project")
        self.assertEqual(kwargs["target_level"], 2)

    def test_repair_dispatches_through_func(self) -> None:
        cmd = _make_cmd("repair points=25")
        mock_rp = MagicMock()
        result = DispatchResult(
            backend=ActionBackend.REGISTRY,
            deferred=False,
            detail=ActionResult(success=True, message="You repair the Lab station."),
        )
        with (
            patch(_ROOM_PROFILE_OBJECTS) as rp_obj,
            patch(_DISPATCH, return_value=result) as dispatch,
        ):
            rp_obj.filter.return_value.first.return_value = mock_rp
            cmd.func()

        dispatch.assert_called_once()
        _, ref, kwargs = dispatch.call_args.args
        self.assertEqual(ref.registry_key, "repair_lab_station")
        self.assertEqual(kwargs["restore_points"], 25)
