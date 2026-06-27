"""Unit tests for CmdSanctum — the ``sanctum <subverb>`` namespace (#1497).

Covers: subverb-map completeness, required-arg missing error paths, and
resolved-kwargs assertions for weave / sever / install (with mocked dispatch).
Mirrors the mock-caller style of ``test_duel_command.py``.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.constants import ActionBackend
from actions.types import ActionResult, DispatchResult
from commands.sanctum import _SUBVERBS, CmdSanctum

_DISPATCH = "commands.command.dispatch_player_action"


def _make_cmd(args: str) -> CmdSanctum:
    cmd = CmdSanctum()
    cmd.caller = MagicMock()
    cmd.caller.location = MagicMock()
    cmd.args = args
    cmd.raw_string = f"sanctum {args}"
    cmd.cmdname = "sanctum"
    return cmd


class SanctumCommandParsingTests(TestCase):
    def test_subverb_map_covers_seven_ops(self) -> None:
        self.assertEqual(
            set(_SUBVERBS),
            {"install", "homecoming", "purging", "weave", "dissolve", "absorb", "sever"},
        )

    def test_weave_requires_slot(self) -> None:
        cmd = CmdSanctum()
        cmd.args = "weave"
        cmd.caller = object()
        with patch.object(CmdSanctum, "msg"):
            cmd.func()  # missing slot → usage message, no dispatch

    def test_unknown_subverb_messages_and_does_not_dispatch(self) -> None:
        cmd = _make_cmd("frobnicate")
        with patch(_DISPATCH) as dispatch:
            cmd.func()
        dispatch.assert_not_called()
        cmd.caller.msg.assert_called()

    def test_bare_sanctum_shows_status_hub(self) -> None:
        cmd = _make_cmd("")
        with (
            patch("actions.definitions.sanctum.sanctum_in_room", return_value=None),
            patch("world.scenes.services.active_persona_for_sheet", return_value=None),
            patch(_DISPATCH) as dispatch,
        ):
            cmd.func()
        dispatch.assert_not_called()
        cmd.caller.msg.assert_called_once()
        self.assertIn("Sanctum actions", cmd.caller.msg.call_args.args[0])

    def test_status_subverb_shows_status_hub(self) -> None:
        cmd = _make_cmd("status")
        with (
            patch("actions.definitions.sanctum.sanctum_in_room", return_value=None),
            patch("world.scenes.services.active_persona_for_sheet", return_value=None),
            patch(_DISPATCH) as dispatch,
        ):
            cmd.func()
        dispatch.assert_not_called()


class SanctumCommandRefTests(TestCase):
    """resolve_action_ref returns a REGISTRY ActionRef for each subverb."""

    def _cmd_with_subverb(self, subverb: str) -> CmdSanctum:
        cmd = _make_cmd(subverb)
        cmd._subverb = subverb
        return cmd

    def test_install_ref(self) -> None:
        cmd = self._cmd_with_subverb("install")
        ref = cmd.resolve_action_ref()
        self.assertEqual(ref.backend, ActionBackend.REGISTRY)
        self.assertEqual(ref.registry_key, "sanctum_install")

    def test_weave_ref(self) -> None:
        ref = self._cmd_with_subverb("weave").resolve_action_ref()
        self.assertEqual(ref.registry_key, "sanctum_weave")

    def test_sever_ref(self) -> None:
        ref = self._cmd_with_subverb("sever").resolve_action_ref()
        self.assertEqual(ref.registry_key, "sanctum_sever")


class SanctumCommandKwargsTests(TestCase):
    """resolve_action_args returns the correct resolved kwargs per subverb."""

    def test_weave_resolves_slot_kind_personal(self) -> None:
        from world.magic.constants import SanctumSlotKind

        cmd = _make_cmd("weave slot=personal")
        cmd._subverb = "weave"
        cmd._rest = "slot=personal"

        mock_sanctum = MagicMock()
        with patch("actions.definitions.sanctum.sanctum_in_room", return_value=mock_sanctum):
            kwargs = cmd.resolve_action_args()

        self.assertEqual(kwargs["sanctum"], mock_sanctum)
        self.assertEqual(kwargs["slot_kind"], SanctumSlotKind.PERSONAL_OWN)

    def test_weave_resolves_slot_kind_covenant(self) -> None:
        from world.magic.constants import SanctumSlotKind

        cmd = _make_cmd("weave slot=covenant")
        cmd._subverb = "weave"
        cmd._rest = "slot=covenant"

        mock_sanctum = MagicMock()
        with patch("actions.definitions.sanctum.sanctum_in_room", return_value=mock_sanctum):
            kwargs = cmd.resolve_action_args()

        self.assertEqual(kwargs["slot_kind"], SanctumSlotKind.COVENANT)

    def test_weave_resolves_slot_kind_helper(self) -> None:
        from world.magic.constants import SanctumSlotKind

        cmd = _make_cmd("weave slot=helper")
        cmd._subverb = "weave"
        cmd._rest = "slot=helper"

        mock_sanctum = MagicMock()
        with patch("actions.definitions.sanctum.sanctum_in_room", return_value=mock_sanctum):
            kwargs = cmd.resolve_action_args()

        self.assertEqual(kwargs["slot_kind"], SanctumSlotKind.HELPER)

    def test_install_resolves_room_profile_and_resonance(self) -> None:
        cmd = _make_cmd("install resonance=Embers owner=personal")
        cmd._subverb = "install"
        cmd._rest = "resonance=Embers owner=personal"

        mock_res = MagicMock()
        mock_rp = MagicMock()

        with (
            patch("world.magic.models.Resonance.objects") as res_obj,
            patch("evennia_extensions.models.RoomProfile.objects") as rp_obj,
        ):
            res_obj.filter.return_value.first.return_value = mock_res
            rp_obj.filter.return_value.first.return_value = mock_rp
            kwargs = cmd.resolve_action_args()

        self.assertEqual(kwargs["resonance"], mock_res)
        self.assertEqual(kwargs["room_profile"], mock_rp)
        self.assertEqual(kwargs["owner_mode"], "PERSONAL")

    def test_install_resolves_covenant_owner_mode(self) -> None:
        cmd = _make_cmd("install resonance=Embers owner=covenant")
        cmd._subverb = "install"
        cmd._rest = "resonance=Embers owner=covenant"

        with (
            patch("world.magic.models.Resonance.objects") as res_obj,
            patch("evennia_extensions.models.RoomProfile.objects") as rp_obj,
        ):
            res_obj.filter.return_value.first.return_value = MagicMock()
            rp_obj.filter.return_value.first.return_value = MagicMock()
            kwargs = cmd.resolve_action_args()

        self.assertEqual(kwargs["owner_mode"], "COVENANT")

    def test_install_missing_owner_raises_command_error(self) -> None:
        from commands.exceptions import CommandError

        cmd = _make_cmd("install resonance=Embers")
        cmd._subverb = "install"
        cmd._rest = "resonance=Embers"

        with (
            patch("world.magic.models.Resonance.objects") as res_obj,
            patch("evennia_extensions.models.RoomProfile.objects"),
        ):
            res_obj.filter.return_value.first.return_value = MagicMock()
            with self.assertRaises(CommandError):
                cmd.resolve_action_args()

    def test_sever_resolves_thread_by_id(self) -> None:
        cmd = _make_cmd("sever thread=42")
        cmd._subverb = "sever"
        cmd._rest = "thread=42"

        mock_sanctum = MagicMock()
        mock_thread = MagicMock()
        mock_thread.pk = 42
        mock_qs = MagicMock()
        mock_qs.filter.return_value.first.return_value = mock_thread

        with (
            patch("actions.definitions.sanctum.sanctum_in_room", return_value=mock_sanctum),
            patch("world.magic.models.Thread.objects") as thread_obj,
        ):
            thread_obj.filter.return_value = mock_qs
            kwargs = cmd.resolve_action_args()

        self.assertEqual(kwargs["thread"], mock_thread)

    def test_sever_resolves_thread_by_name(self) -> None:
        cmd = _make_cmd("sever thread=ember-coil")
        cmd._subverb = "sever"
        cmd._rest = "thread=ember-coil"

        mock_sanctum = MagicMock()
        mock_thread = MagicMock()
        mock_qs = MagicMock()
        # "ember-coil" is not a digit, so only name filter is tried
        mock_qs.filter.return_value.first.return_value = mock_thread

        with (
            patch("actions.definitions.sanctum.sanctum_in_room", return_value=mock_sanctum),
            patch("world.magic.models.Thread.objects") as thread_obj,
        ):
            thread_obj.filter.return_value = mock_qs
            kwargs = cmd.resolve_action_args()

        self.assertEqual(kwargs["thread"], mock_thread)

    def test_sever_missing_thread_arg_raises_command_error(self) -> None:
        from commands.exceptions import CommandError

        cmd = _make_cmd("sever")
        cmd._subverb = "sever"
        cmd._rest = ""

        mock_sanctum = MagicMock()
        with patch("actions.definitions.sanctum.sanctum_in_room", return_value=mock_sanctum):
            with self.assertRaises(CommandError):
                cmd.resolve_action_args()

    def test_dissolve_passes_sanctum(self) -> None:
        cmd = _make_cmd("dissolve")
        cmd._subverb = "dissolve"
        cmd._rest = ""

        mock_sanctum = MagicMock()
        with patch("actions.definitions.sanctum.sanctum_in_room", return_value=mock_sanctum):
            kwargs = cmd.resolve_action_args()

        self.assertEqual(kwargs["sanctum"], mock_sanctum)

    def test_absorb_passes_sanctum(self) -> None:
        cmd = _make_cmd("absorb")
        cmd._subverb = "absorb"
        cmd._rest = ""

        mock_sanctum = MagicMock()
        with patch("actions.definitions.sanctum.sanctum_in_room", return_value=mock_sanctum):
            kwargs = cmd.resolve_action_args()

        self.assertEqual(kwargs["sanctum"], mock_sanctum)

    def test_homecoming_resolves_amount_and_narrative(self) -> None:
        cmd = _make_cmd("homecoming amount=5 narrative=The fire remembers")
        cmd._subverb = "homecoming"
        cmd._rest = "amount=5 narrative=The fire remembers"

        mock_sanctum = MagicMock()
        with patch("actions.definitions.sanctum.sanctum_in_room", return_value=mock_sanctum):
            kwargs = cmd.resolve_action_args()

        self.assertEqual(kwargs["sanctum"], mock_sanctum)
        self.assertEqual(kwargs["resonance_sacrificed"], 5)
        self.assertEqual(kwargs["narrative_text"], "The fire remembers")

    def test_homecoming_missing_amount_raises_command_error(self) -> None:
        from commands.exceptions import CommandError

        cmd = _make_cmd("homecoming")
        cmd._subverb = "homecoming"
        cmd._rest = ""

        mock_sanctum = MagicMock()
        with patch("actions.definitions.sanctum.sanctum_in_room", return_value=mock_sanctum):
            with self.assertRaises(CommandError):
                cmd.resolve_action_args()


class SanctumCommandDispatchTests(TestCase):
    """Full func() dispatch tests — mock dispatch_player_action to assert kwargs."""

    def test_weave_dispatches_with_slot_kind(self) -> None:
        from world.magic.constants import SanctumSlotKind

        cmd = _make_cmd("weave slot=personal")
        mock_sanctum = MagicMock()
        result = DispatchResult(
            backend=ActionBackend.REGISTRY,
            deferred=False,
            detail=ActionResult(success=True, message="Thread woven."),
        )
        with (
            patch("actions.definitions.sanctum.sanctum_in_room", return_value=mock_sanctum),
            patch(_DISPATCH, return_value=result) as dispatch,
        ):
            cmd.func()

        dispatch.assert_called_once()
        _, _ref, kwargs = dispatch.call_args.args
        self.assertEqual(kwargs["slot_kind"], SanctumSlotKind.PERSONAL_OWN)
        self.assertEqual(kwargs["sanctum"], mock_sanctum)

    def test_install_dispatches_through_func(self) -> None:
        cmd = _make_cmd("install resonance=Embers owner=personal")
        mock_res = MagicMock()
        mock_rp = MagicMock()
        result = DispatchResult(
            backend=ActionBackend.REGISTRY,
            deferred=False,
            detail=ActionResult(success=True, message="Sanctum installed."),
        )
        with (
            patch("world.magic.models.Resonance.objects") as res_obj,
            patch("evennia_extensions.models.RoomProfile.objects") as rp_obj,
            patch(_DISPATCH, return_value=result) as dispatch,
        ):
            res_obj.filter.return_value.first.return_value = mock_res
            rp_obj.filter.return_value.first.return_value = mock_rp
            cmd.func()

        dispatch.assert_called_once()
        _, ref, kwargs = dispatch.call_args.args
        self.assertEqual(ref.registry_key, "sanctum_install")
        self.assertEqual(kwargs["owner_mode"], "PERSONAL")
        self.assertEqual(kwargs["resonance"], mock_res)

    def test_sever_dispatches_with_thread(self) -> None:
        cmd = _make_cmd("sever thread=99")
        mock_sanctum = MagicMock()
        mock_thread = MagicMock()
        mock_qs = MagicMock()
        mock_qs.filter.return_value.first.return_value = mock_thread

        result = DispatchResult(
            backend=ActionBackend.REGISTRY,
            deferred=False,
            detail=ActionResult(success=True, message="Thread severed."),
        )
        with (
            patch("actions.definitions.sanctum.sanctum_in_room", return_value=mock_sanctum),
            patch("world.magic.models.Thread.objects") as thread_obj,
            patch(_DISPATCH, return_value=result) as dispatch,
        ):
            thread_obj.filter.return_value = mock_qs
            cmd.func()

        dispatch.assert_called_once()
        _, ref, kwargs = dispatch.call_args.args
        self.assertEqual(ref.registry_key, "sanctum_sever")
        self.assertEqual(kwargs["thread"], mock_thread)
