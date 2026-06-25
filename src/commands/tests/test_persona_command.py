"""Unit tests for CmdPersona — list faces + wear-face switch (#1347).

Mirrors src/commands/tests/test_combat_commands.py +
src/commands/tests/test_dispatch_command.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.constants import ActionBackend
from actions.types import ActionResult, DispatchResult
from commands.exceptions import CommandError
from commands.persona import CmdPersona
from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.constants import PersonaType
from world.scenes.factories import PersonaFactory


def _cmd(caller, args=""):
    cmd = CmdPersona()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"persona {args}".strip()
    cmd.cmdname = "persona"
    return cmd


class CmdPersonaTests(TestCase):
    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.character.msg = MagicMock()
        self.alt = PersonaFactory(
            character_sheet=self.sheet, persona_type=PersonaType.ESTABLISHED, name="Alt Face"
        )

    def test_bare_lists_personas_marks_active(self) -> None:
        _cmd(self.character).func()
        sent = "\n".join(str(c.args[0]) for c in self.character.msg.call_args_list)
        self.assertIn("Alt Face", sent)
        self.assertIn(self.sheet.primary_persona.name, sent)
        self.assertIn("active", sent)

    def test_list_arg_lists_personas(self) -> None:
        """'persona list' also shows the listing."""
        _cmd(self.character, "list").func()
        sent = "\n".join(str(c.args[0]) for c in self.character.msg.call_args_list)
        self.assertIn("Alt Face", sent)
        self.assertIn("active", sent)

    def test_named_dispatches_set_active(self) -> None:
        cmd = _cmd(self.character, "Alt Face")
        with patch("commands.command.dispatch_player_action") as disp:
            disp.return_value = DispatchResult(
                backend=ActionBackend.REGISTRY,
                deferred=False,
                detail=ActionResult(success=True, message="ok"),
            )
            cmd.func()
        ref = disp.call_args.args[1]
        kwargs = disp.call_args.args[2]
        self.assertEqual(ref.backend, ActionBackend.REGISTRY)
        self.assertEqual(ref.registry_key, "set_active_persona")
        self.assertEqual(kwargs, {"persona_id": self.alt.pk})

    def test_unknown_name_raises(self) -> None:
        cmd = _cmd(self.character, "Nobody")
        cmd._name = "Nobody"
        with self.assertRaises(CommandError):
            cmd.resolve_action_args()

    def test_case_insensitive_name_match(self) -> None:
        """Matching is case-insensitive."""
        cmd = _cmd(self.character, "alt face")
        with patch("commands.command.dispatch_player_action") as disp:
            disp.return_value = DispatchResult(
                backend=ActionBackend.REGISTRY,
                deferred=False,
                detail=ActionResult(success=True, message="ok"),
            )
            cmd.func()
        kwargs = disp.call_args.args[2]
        self.assertEqual(kwargs, {"persona_id": self.alt.pk})


class CmdPersonaCmdsetRegistrationTests(TestCase):
    def test_persona_command_registered(self) -> None:
        from commands.default_cmdsets import CharacterCmdSet

        cmdset = CharacterCmdSet()
        cmdset.at_cmdset_creation()
        keys = {c.key for c in cmdset.commands}
        self.assertIn("persona", keys)
