"""Unit tests for CmdForm — list, shift, revert alternate selves (#1111 slice 4)."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.constants import ActionBackend
from actions.types import ActionResult, DispatchResult
from commands.exceptions import CommandError
from commands.form import CmdForm
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.models import CharacterSheet
from world.forms.factories import (
    ActiveAlternateSelfFactory,
    AlternateSelfFactory,
    CharacterFormFactory,
    CharacterFormStateFactory,
)
from world.forms.models import AlternateSelf, FormType


def _cmd(caller, args=""):
    cmd = CmdForm()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"form {args}".strip()
    cmd.cmdname = "form"
    return cmd


class CmdFormTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.character = cls.sheet.character
        cls.true_form = CharacterFormFactory(
            character=cls.character, name="True", form_type=FormType.TRUE
        )
        CharacterFormStateFactory(character=cls.character, active_form=cls.true_form)
        cls.alt_self = AlternateSelfFactory(character=cls.sheet, display_name="the Beast")

    def setUp(self):
        self.character = cast(Any, type(self).character)
        self.character.msg = MagicMock()

    def _typed_sheet(self) -> CharacterSheet:
        return cast(CharacterSheet, type(self).sheet)

    def _typed_alt(self) -> AlternateSelf:
        return cast(AlternateSelf, type(self).alt_self)

    def test_bare_form_shows_hub(self):
        _cmd(self.character).func()
        sent = "\n".join(str(c.args[0]) for c in self.character.msg.call_args_list)
        self.assertIn("true self", sent)
        self.assertIn("the Beast", sent)

    def test_list_arg_shows_hub(self):
        _cmd(self.character, "list").func()
        sent = "\n".join(str(c.args[0]) for c in self.character.msg.call_args_list)
        self.assertIn("Available alternate selves", sent)
        self.assertIn("the Beast", sent)

    def test_form_shift_dispatches_with_resolved_pk(self):
        cmd = _cmd(self.character, "shift the Beast")
        with patch("commands.command.dispatch_player_action") as disp:
            disp.return_value = DispatchResult(
                backend=ActionBackend.REGISTRY,
                deferred=False,
                detail=ActionResult(success=True, message="You assume the Beast."),
            )
            cmd.func()
        ref = disp.call_args.args[1]
        kwargs = disp.call_args.args[2]
        self.assertEqual(ref.backend, ActionBackend.REGISTRY)
        self.assertEqual(ref.registry_key, "shift_form")
        self.assertEqual(kwargs, {"alternate_self_id": self._typed_alt().pk})

    def test_form_shift_by_id_falls_back_to_pk(self):
        cmd = _cmd(self.character, f"shift {self._typed_alt().pk}")
        with patch("commands.command.dispatch_player_action") as disp:
            disp.return_value = DispatchResult(
                backend=ActionBackend.REGISTRY,
                deferred=False,
                detail=ActionResult(success=True, message="ok"),
            )
            cmd.func()
        kwargs = disp.call_args.args[2]
        self.assertEqual(kwargs, {"alternate_self_id": self._typed_alt().pk})

    def test_form_shift_unknown_name_lists_available(self):
        cmd = _cmd(self.character, "shift Nobody")
        cmd._name = "Nobody"
        with self.assertRaises(CommandError) as ctx:
            cmd.resolve_action_args()
        self.assertIn("No alternate self named 'Nobody'", str(ctx.exception))
        self.assertIn("Available: the Beast", str(ctx.exception))

    def test_form_shift_ambiguous_case_collision_raises(self):
        AlternateSelfFactory(character=self._typed_sheet(), display_name="The Beast")
        cmd = _cmd(self.character, "shift the beast")
        cmd._name = "the beast"
        with self.assertRaises(CommandError) as ctx:
            cmd.resolve_action_args()
        self.assertIn("Multiple alternate selves match", str(ctx.exception))

    def test_form_shift_requires_name(self):
        cmd = _cmd(self.character, "shift")
        with self.assertRaises(CommandError):
            cmd.func()

    def test_form_revert_dispatches_no_kwargs(self):
        ActiveAlternateSelfFactory(character=self._typed_sheet(), alternate_self=self._typed_alt())
        cmd = _cmd(self.character, "revert")
        with patch("commands.command.dispatch_player_action") as disp:
            disp.return_value = DispatchResult(
                backend=ActionBackend.REGISTRY,
                deferred=False,
                detail=ActionResult(success=True, message="You revert to your true self."),
            )
            cmd.func()
        ref = disp.call_args.args[1]
        kwargs = disp.call_args.args[2]
        self.assertEqual(ref.registry_key, "revert_form")
        self.assertEqual(kwargs, {})

    def test_form_hub_shows_active_alt_self(self):
        ActiveAlternateSelfFactory(character=self._typed_sheet(), alternate_self=self._typed_alt())
        _cmd(self.character).func()
        sent = "\n".join(str(c.args[0]) for c in self.character.msg.call_args_list)
        self.assertIn("You are in the Beast", sent)
        self.assertIn("Available alternate selves", sent)
        self.assertIn("the Beast", sent)

    def test_form_hub_shows_blocked_when_not_in_control(self):
        fake_condition = MagicMock()
        fake_condition.condition.category.alters_behavior = True
        with patch.object(self.character.conditions, "active", return_value=[fake_condition]):
            _cmd(self.character).func()
        sent = "\n".join(str(c.args[0]) for c in self.character.msg.call_args_list)
        self.assertIn("not in control", sent)
        self.assertIn("revert is blocked", sent)


class CmdFormCmdsetRegistrationTests(TestCase):
    def test_form_command_registered(self):
        from commands.default_cmdsets import CharacterCmdSet

        cmdset = CharacterCmdSet()
        cmdset.at_cmdset_creation()
        keys = {c.key for c in cmdset.commands}
        self.assertIn("form", keys)
