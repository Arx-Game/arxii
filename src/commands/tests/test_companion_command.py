"""Unit tests for CmdCompanion — the ``companion <subverb>`` namespace (#1918).

Covers: subverb-map completeness, required-arg missing error paths, resolved-kwargs
assertions for bind / release / fight / deploy, and full func() dispatch with mocked
``dispatch_player_action``. Mirrors the mock-caller style of ``test_sanctum_command.py``
and ``test_combat_maneuvers_command.py``.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.constants import ActionBackend
from actions.types import ActionResult, DispatchResult
from commands.companion import _SUBVERBS, CmdCompanion
from commands.exceptions import CommandError

_DISPATCH = "commands.command.dispatch_player_action"


def _make_cmd(args: str) -> CmdCompanion:
    cmd = CmdCompanion()
    cmd.caller = MagicMock()
    cmd.args = args
    cmd.raw_string = f"companion {args}"
    cmd.cmdname = "companion"
    return cmd


class CompanionCommandParsingTests(TestCase):
    def test_subverb_map_covers_four_ops(self) -> None:
        self.assertEqual(set(_SUBVERBS), {"bind", "fight", "deploy", "release"})

    def test_unknown_subverb_messages_and_does_not_dispatch(self) -> None:
        cmd = _make_cmd("frobnicate")
        with patch(_DISPATCH) as dispatch:
            cmd.func()
        dispatch.assert_not_called()
        cmd.caller.msg.assert_called()

    def test_bare_companion_shows_status_hub(self) -> None:
        cmd = _make_cmd("")
        with patch(_DISPATCH) as dispatch:
            cmd.func()
        dispatch.assert_not_called()
        cmd.caller.msg.assert_called_once()
        self.assertIn("Companion actions", cmd.caller.msg.call_args.args[0])

    def test_status_subverb_shows_status_hub(self) -> None:
        cmd = _make_cmd("status")
        with patch(_DISPATCH) as dispatch:
            cmd.func()
        dispatch.assert_not_called()
        cmd.caller.msg.assert_called_once()

    def test_list_subverb_shows_status_hub(self) -> None:
        cmd = _make_cmd("list")
        with patch(_DISPATCH) as dispatch:
            cmd.func()
        dispatch.assert_not_called()
        cmd.caller.msg.assert_called_once()


class CompanionCommandRefTests(TestCase):
    """resolve_action_ref returns a REGISTRY ActionRef for each subverb."""

    def _cmd_with_subverb(self, subverb: str) -> CmdCompanion:
        cmd = _make_cmd(subverb)
        cmd._subverb = subverb
        return cmd

    def test_bind_ref(self) -> None:
        ref = self._cmd_with_subverb("bind").resolve_action_ref()
        self.assertEqual(ref.backend, ActionBackend.REGISTRY)
        self.assertEqual(ref.registry_key, "bind_companion")

    def test_fight_ref(self) -> None:
        ref = self._cmd_with_subverb("fight").resolve_action_ref()
        self.assertEqual(ref.registry_key, "companion_fight")

    def test_deploy_ref(self) -> None:
        ref = self._cmd_with_subverb("deploy").resolve_action_ref()
        self.assertEqual(ref.registry_key, "deploy_companion")

    def test_release_ref(self) -> None:
        ref = self._cmd_with_subverb("release").resolve_action_ref()
        self.assertEqual(ref.registry_key, "release_companion")


class CompanionCommandKwargsTests(TestCase):
    """resolve_action_args returns the correct resolved kwargs per subverb."""

    def test_bind_resolves_archetype_gift_and_name(self) -> None:
        cmd = _make_cmd("bind archetype=Hawk gift=Beastlord name=Skree")
        cmd._subverb = "bind"
        cmd._rest = "archetype=Hawk gift=Beastlord name=Skree"

        mock_sheet = MagicMock()
        cmd.caller.sheet_data = mock_sheet
        mock_archetype = MagicMock()
        mock_archetype.pk = 7
        mock_gift = MagicMock()
        mock_gift.pk = 3
        mock_char_gift = MagicMock()
        mock_char_gift.gift = mock_gift

        with (
            patch("world.companions.models.CompanionArchetype.objects") as arch_obj,
            patch("world.magic.models.gifts.CharacterGift.objects") as cg_obj,
        ):
            arch_obj.filter.return_value.first.return_value = mock_archetype
            # gift resolution: _resolve_by_name_or_pk chains .filter().filter().first()
            cg_obj.filter.return_value.filter.return_value.first.return_value = mock_char_gift

            kwargs = cmd.resolve_action_args()

        self.assertEqual(kwargs["archetype_id"], 7)
        self.assertEqual(kwargs["gift_id"], 3)
        self.assertEqual(kwargs["name"], "Skree")

    def test_bind_name_greedy_consumes_spaces(self) -> None:
        cmd = _make_cmd("bind archetype=Hawk gift=Beastlord name=Brave Hawk")
        cmd._subverb = "bind"
        cmd._rest = "archetype=Hawk gift=Beastlord name=Brave Hawk"

        cmd.caller.sheet_data = MagicMock()
        mock_archetype = MagicMock()
        mock_archetype.pk = 1
        mock_gift = MagicMock()
        mock_gift.pk = 2
        mock_char_gift = MagicMock()
        mock_char_gift.gift = mock_gift

        with (
            patch("world.companions.models.CompanionArchetype.objects") as arch_obj,
            patch("world.magic.models.gifts.CharacterGift.objects") as cg_obj,
        ):
            arch_obj.filter.return_value.first.return_value = mock_archetype
            cg_obj.filter.return_value.filter.return_value.first.return_value = mock_char_gift

            kwargs = cmd.resolve_action_args()

        self.assertEqual(kwargs["name"], "Brave Hawk")

    def test_bind_missing_name_raises_command_error(self) -> None:
        cmd = _make_cmd("bind archetype=Hawk gift=Beastlord")
        cmd._subverb = "bind"
        cmd._rest = "archetype=Hawk gift=Beastlord"

        cmd.caller.sheet_data = MagicMock()
        mock_archetype = MagicMock()
        mock_archetype.pk = 1
        mock_char_gift = MagicMock()
        mock_char_gift.gift = MagicMock(pk=2)

        with (
            patch("world.companions.models.CompanionArchetype.objects") as arch_obj,
            patch("world.magic.models.gifts.CharacterGift.objects") as cg_obj,
        ):
            arch_obj.filter.return_value.first.return_value = mock_archetype
            cg_obj.filter.return_value.filter.return_value.first.return_value = mock_char_gift

            with self.assertRaises(CommandError):
                cmd.resolve_action_args()

    def test_bind_missing_archetype_raises_command_error(self) -> None:
        cmd = _make_cmd("bind gift=Beastlord name=Skree")
        cmd._subverb = "bind"
        cmd._rest = "gift=Beastlord name=Skree"

        with self.assertRaises(CommandError):
            cmd.resolve_action_args()

    def test_release_resolves_companion_id_by_id(self) -> None:
        cmd = _make_cmd("release 42")
        cmd._subverb = "release"
        cmd._rest = "42"

        cmd.caller.sheet_data = MagicMock()
        mock_companion = MagicMock()
        mock_companion.pk = 42

        with patch("world.companions.models.Companion.objects") as comp_obj:
            qs = MagicMock()
            qs.filter.return_value.first.return_value = mock_companion
            comp_obj.filter.return_value = qs

            kwargs = cmd.resolve_action_args()

        self.assertEqual(kwargs["companion_id"], 42)

    def test_release_resolves_companion_id_by_name(self) -> None:
        cmd = _make_cmd("release Skree")
        cmd._subverb = "release"
        cmd._rest = "Skree"

        cmd.caller.sheet_data = MagicMock()
        mock_companion = MagicMock()
        mock_companion.pk = 99

        with patch("world.companions.models.Companion.objects") as comp_obj:
            qs = MagicMock()
            qs.filter.return_value.first.return_value = mock_companion
            comp_obj.filter.return_value = qs

            kwargs = cmd.resolve_action_args()

        self.assertEqual(kwargs["companion_id"], 99)

    def test_release_missing_arg_raises_command_error(self) -> None:
        cmd = _make_cmd("release")
        cmd._subverb = "release"
        cmd._rest = ""

        cmd.caller.sheet_data = MagicMock()
        with self.assertRaises(CommandError):
            cmd.resolve_action_args()

    def test_release_not_found_raises_command_error(self) -> None:
        cmd = _make_cmd("release Ghost")
        cmd._subverb = "release"
        cmd._rest = "Ghost"

        cmd.caller.sheet_data = MagicMock()
        with patch("world.companions.models.Companion.objects") as comp_obj:
            qs = MagicMock()
            qs.filter.return_value.first.return_value = None
            comp_obj.filter.return_value = qs

            with self.assertRaises(CommandError):
                cmd.resolve_action_args()

    def test_fight_resolves_companion_id(self) -> None:
        cmd = _make_cmd("fight Skree")
        cmd._subverb = "fight"
        cmd._rest = "Skree"

        cmd.caller.sheet_data = MagicMock()
        mock_companion = MagicMock()
        mock_companion.pk = 5

        with patch("world.companions.models.Companion.objects") as comp_obj:
            qs = MagicMock()
            qs.filter.return_value.first.return_value = mock_companion
            comp_obj.filter.return_value = qs

            kwargs = cmd.resolve_action_args()

        self.assertEqual(kwargs["companion_id"], 5)

    def test_deploy_resolves_companion_id(self) -> None:
        cmd = _make_cmd("deploy Skree")
        cmd._subverb = "deploy"
        cmd._rest = "Skree"

        cmd.caller.sheet_data = MagicMock()
        mock_companion = MagicMock()
        mock_companion.pk = 8

        with patch("world.companions.models.Companion.objects") as comp_obj:
            qs = MagicMock()
            qs.filter.return_value.first.return_value = mock_companion
            comp_obj.filter.return_value = qs

            kwargs = cmd.resolve_action_args()

        self.assertEqual(kwargs["companion_id"], 8)


class CompanionCommandDispatchTests(TestCase):
    """Full func() dispatch tests — mock dispatch_player_action to assert kwargs."""

    def test_release_dispatches_with_companion_id(self) -> None:
        cmd = _make_cmd("release 42")
        cmd.caller.sheet_data = MagicMock()
        mock_companion = MagicMock()
        mock_companion.pk = 42
        result = DispatchResult(
            backend=ActionBackend.REGISTRY,
            deferred=False,
            detail=ActionResult(success=True, message="Skree is released."),
        )
        with (
            patch("world.companions.models.Companion.objects") as comp_obj,
            patch(_DISPATCH, return_value=result) as dispatch,
        ):
            qs = MagicMock()
            qs.filter.return_value.first.return_value = mock_companion
            comp_obj.filter.return_value = qs
            cmd.func()

        dispatch.assert_called_once()
        _, ref, kwargs = dispatch.call_args.args
        self.assertEqual(ref.registry_key, "release_companion")
        self.assertEqual(kwargs["companion_id"], 42)

    def test_bind_dispatches_with_resolved_kwargs(self) -> None:
        cmd = _make_cmd("bind archetype=Hawk gift=Beastlord name=Skree")
        cmd.caller.sheet_data = MagicMock()
        mock_archetype = MagicMock()
        mock_archetype.pk = 7
        mock_gift = MagicMock()
        mock_gift.pk = 3
        mock_char_gift = MagicMock()
        mock_char_gift.gift = mock_gift
        result = DispatchResult(
            backend=ActionBackend.REGISTRY,
            deferred=False,
            detail=ActionResult(success=True, message="Skree the Hawk is now bonded."),
        )
        with (
            patch("world.companions.models.CompanionArchetype.objects") as arch_obj,
            patch("world.magic.models.gifts.CharacterGift.objects") as cg_obj,
            patch(_DISPATCH, return_value=result) as dispatch,
        ):
            arch_obj.filter.return_value.first.return_value = mock_archetype
            cg_obj.filter.return_value.filter.return_value.first.return_value = mock_char_gift

            cmd.func()

        dispatch.assert_called_once()
        _, ref, kwargs = dispatch.call_args.args
        self.assertEqual(ref.registry_key, "bind_companion")
        self.assertEqual(kwargs["archetype_id"], 7)
        self.assertEqual(kwargs["gift_id"], 3)
        self.assertEqual(kwargs["name"], "Skree")

    def test_fight_dispatches_with_companion_id(self) -> None:
        cmd = _make_cmd("fight Skree")
        cmd.caller.sheet_data = MagicMock()
        mock_companion = MagicMock()
        mock_companion.pk = 11
        result = DispatchResult(
            backend=ActionBackend.REGISTRY,
            deferred=False,
            detail=ActionResult(success=True, message="Skree joins the fight!"),
        )
        with (
            patch("world.companions.models.Companion.objects") as comp_obj,
            patch(_DISPATCH, return_value=result) as dispatch,
        ):
            qs = MagicMock()
            qs.filter.return_value.first.return_value = mock_companion
            comp_obj.filter.return_value = qs
            cmd.func()

        dispatch.assert_called_once()
        _, ref, kwargs = dispatch.call_args.args
        self.assertEqual(ref.registry_key, "companion_fight")
        self.assertEqual(kwargs["companion_id"], 11)

    def test_deploy_dispatches_with_companion_id(self) -> None:
        cmd = _make_cmd("deploy Skree")
        cmd.caller.sheet_data = MagicMock()
        mock_companion = MagicMock()
        mock_companion.pk = 14
        result = DispatchResult(
            backend=ActionBackend.REGISTRY,
            deferred=False,
            detail=ActionResult(success=True, message="Skree is deployed!"),
        )
        with (
            patch("world.companions.models.Companion.objects") as comp_obj,
            patch(_DISPATCH, return_value=result) as dispatch,
        ):
            qs = MagicMock()
            qs.filter.return_value.first.return_value = mock_companion
            comp_obj.filter.return_value = qs
            cmd.func()

        dispatch.assert_called_once()
        _, ref, kwargs = dispatch.call_args.args
        self.assertEqual(ref.registry_key, "deploy_companion")
        self.assertEqual(kwargs["companion_id"], 14)


class CompanionCommandStatusHubTests(TestCase):
    """The status hub lists active companions + capacity."""

    def test_no_sheet_shows_actions_header(self) -> None:
        cmd = _make_cmd("")
        cmd.caller.sheet_data = None
        with patch(_DISPATCH) as dispatch:
            cmd.func()
        dispatch.assert_not_called()
        cmd.caller.msg.assert_called_once()
        self.assertIn("Companion actions", cmd.caller.msg.call_args.args[0])

    def test_no_active_companions_shows_empty_message(self) -> None:
        cmd = _make_cmd("")
        cmd.caller.sheet_data = MagicMock()
        cmd.caller.companions.active.return_value = []
        cmd.caller.sheet_data.character_gifts.all.return_value = []
        with patch(_DISPATCH) as dispatch:
            cmd.func()
        dispatch.assert_not_called()
        msg = cmd.caller.msg.call_args.args[0]
        self.assertIn("no active companions", msg)
