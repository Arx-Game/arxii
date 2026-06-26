"""Unit tests for ``CmdDeed`` — spread / story telnet namespace (#1503)."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.constants import ActionBackend
from actions.types import ActionResult, DispatchResult
from commands.deeds import CmdDeed
from commands.exceptions import CommandError
from world.character_sheets.factories import CharacterSheetFactory


def _cmd(caller, args=""):
    cmd = CmdDeed()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"deed {args}".strip()
    cmd.cmdname = "deed"
    return cmd


class CmdDeedTests(TestCase):
    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.character.msg = MagicMock()
        self.persona = self.sheet.primary_persona
        self.deed = SimpleNamespace(pk=101)
        self.spec = SimpleNamespace(pk=202)

    def _patch_helpers(self, cmd):
        """Make resolve helpers return controlled fixtures."""
        cmd._resolve_deed = MagicMock(return_value=self.deed)
        cmd._resolve_specialization = MagicMock(return_value=self.spec)
        cmd._current_scene_id = MagicMock(return_value=303)

    def test_spread_parses_and_dispatches(self):
        cmd = _cmd(self.character, "spread Test Deed effort=high specialization=Song pose=A song.")
        self._patch_helpers(cmd)
        with patch("commands.command.dispatch_player_action") as disp:
            disp.return_value = DispatchResult(
                backend=ActionBackend.SCENE_ADAPTIVE,
                deferred=False,
                detail=ActionResult(success=True, message="You spread the tale."),
            )
            cmd.func()

        ref = disp.call_args.args[1]
        kwargs = disp.call_args.args[2]
        self.assertEqual(ref.backend, ActionBackend.SCENE_ADAPTIVE)
        self.assertEqual(ref.registry_key, "spread_tale")
        self.assertEqual(kwargs["persona_id"], self.persona.pk)
        self.assertEqual(kwargs["scene_id"], 303)
        self.assertEqual(kwargs["deed_id"], 101)
        self.assertEqual(kwargs["effort_level"], "high")
        self.assertEqual(kwargs["specialization_id"], 202)
        self.assertEqual(kwargs["pose_text"], "A song.")

    def test_spread_bare_deed_defaults(self):
        cmd = _cmd(self.character, "spread 47")
        self._patch_helpers(cmd)
        with patch("commands.command.dispatch_player_action") as disp:
            disp.return_value = DispatchResult(
                backend=ActionBackend.SCENE_ADAPTIVE,
                deferred=False,
                detail=ActionResult(success=True, message="Spread."),
            )
            cmd.func()

        kwargs = disp.call_args.args[2]
        self.assertEqual(kwargs["effort_level"], "medium")
        self.assertIsNone(kwargs["specialization_id"])
        self.assertEqual(kwargs["pose_text"], "")

    def test_spread_rejects_bare_command(self):
        cmd = _cmd(self.character, "spread")
        cmd.func()
        self.assertTrue(
            any("Spread what deed?" in str(c.args[0]) for c in self.character.msg.call_args_list)
        )

    def test_story_parses_and_dispatches(self):
        cmd = _cmd(self.character, "story Test Deed=I was there.")
        cmd._resolve_deed = MagicMock(return_value=self.deed)
        with patch("commands.command.dispatch_player_action") as disp:
            disp.return_value = DispatchResult(
                backend=ActionBackend.SCENE_ADAPTIVE,
                deferred=False,
                detail=ActionResult(success=True, message="Saved."),
            )
            cmd.func()

        ref = disp.call_args.args[1]
        kwargs = disp.call_args.args[2]
        self.assertEqual(ref.registry_key, "save_deed_story")
        self.assertEqual(kwargs["persona_id"], self.persona.pk)
        self.assertEqual(kwargs["deed_id"], 101)
        self.assertEqual(kwargs["text"], "I was there.")

    def test_story_rejects_missing_equals(self):
        cmd = _cmd(self.character, "story Test Deed")
        cmd._resolve_deed = MagicMock(return_value=self.deed)
        cmd.func()
        self.assertTrue(
            any("Record a story how?" in str(c.args[0]) for c in self.character.msg.call_args_list)
        )

    def test_unknown_subverb_rejects(self):
        cmd = _cmd(self.character, "dance")
        with self.assertRaises(CommandError):
            cmd.func()


class CmdDeedCmdsetRegistrationTests(TestCase):
    def test_deed_command_registered(self) -> None:
        from commands.default_cmdsets import CharacterCmdSet

        cmdset = CharacterCmdSet()
        cmdset.at_cmdset_creation()
        keys = {c.key for c in cmdset.commands}
        self.assertIn("deed", keys)
