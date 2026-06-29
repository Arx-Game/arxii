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

    def test_ambiguous_case_collision_raises(self) -> None:
        """Two own personas whose names differ only in case → CommandError (>1 iexact match)."""
        PersonaFactory(
            character_sheet=self.sheet, persona_type=PersonaType.ESTABLISHED, name="Echo"
        )
        PersonaFactory(
            character_sheet=self.sheet, persona_type=PersonaType.ESTABLISHED, name="echo"
        )
        cmd = _cmd(self.character, "echo")
        cmd._name = "echo"
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


class CmdPersonaCreateTests(TestCase):
    """`persona create <name>` / `persona mask <name>` — the #1127 creation subverbs."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.character.msg = MagicMock()

    def test_create_makes_an_established_persona(self) -> None:
        from world.scenes.models import Persona

        _cmd(self.character, "create Robert D'Vile").func()
        assert Persona.objects.filter(
            character_sheet=self.sheet, name="Robert D'Vile", persona_type=PersonaType.ESTABLISHED
        ).exists()

    def test_mask_makes_a_temporary_face_and_wears_it(self) -> None:
        from world.scenes.models import Persona

        _cmd(self.character, "mask A Masked Figure").func()
        mask = Persona.objects.get(character_sheet=self.sheet, name="A Masked Figure")
        assert mask.persona_type == PersonaType.TEMPORARY
        assert mask.is_fake_name is True
        self.sheet.refresh_from_db()
        assert self.sheet.active_persona_id == mask.pk

    def test_create_without_a_name_shows_usage(self) -> None:
        _cmd(self.character, "create").func()
        sent = "\n".join(str(c.args[0]) for c in self.character.msg.call_args_list)
        self.assertIn("Usage: persona create", sent)


class CmdPersonaProfileTests(TestCase):
    """`persona profile <name> [field=value …]` — view/author a cover's guise bio (#1270)."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.character.msg = MagicMock()
        self.cover = PersonaFactory(
            character_sheet=self.sheet, persona_type=PersonaType.ESTABLISHED, name="Robert"
        )

    def _sent(self) -> str:
        return "\n".join(str(c.args[0]) for c in self.character.msg.call_args_list)

    def test_authors_the_guise_bio(self) -> None:
        _cmd(self.character, "profile Robert concept=A wine merchant quote=In vino veritas").func()
        self.cover.refresh_from_db()
        assert self.cover.profile is not None
        assert self.cover.profile.concept == "A wine merchant"
        assert self.cover.profile.quote == "In vino veritas"

    def test_shows_the_guise_bio_after_authoring(self) -> None:
        _cmd(self.character, "profile Robert concept=A wine merchant").func()
        self.character.msg.reset_mock()
        _cmd(self.character, "profile Robert").func()
        self.assertIn("A wine merchant", self._sent())

    def test_unauthored_guise_prompts_to_create(self) -> None:
        _cmd(self.character, "profile Robert").func()
        self.assertIn("no guise bio yet", self._sent())

    def test_cannot_author_a_guise_for_the_primary_face(self) -> None:
        primary = self.sheet.primary_persona
        _cmd(self.character, f"profile {primary.name} concept=nope").func()
        self.assertIn("true face", self._sent().lower())


class CmdPersonaActiveNoneTests(TestCase):
    """Listing must not crash when active_persona_for_sheet returns None."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.character.msg = MagicMock()
        PersonaFactory(
            character_sheet=self.sheet, persona_type=PersonaType.ESTABLISHED, name="Alt Face"
        )

    def test_listing_does_not_crash_when_active_is_none(self) -> None:
        """No AttributeError when active_persona_for_sheet returns None."""
        with patch(
            "world.scenes.services.active_persona_for_sheet",  # noqa: STRING_LITERAL
            return_value=None,
        ):
            _cmd(self.character).func()
        sent = "\n".join(str(c.args[0]) for c in self.character.msg.call_args_list)
        self.assertIn("Alt Face", sent)
        self.assertNotIn("active", sent)


class CmdPersonaCmdsetRegistrationTests(TestCase):
    def test_persona_command_registered(self) -> None:
        from commands.default_cmdsets import CharacterCmdSet

        cmdset = CharacterCmdSet()
        cmdset.at_cmdset_creation()
        keys = {c.key for c in cmdset.commands}
        self.assertIn("persona", keys)
