"""Tests for the telnet ``magescar`` command (#1490)."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.types import ActionResult
from commands.alterations import CmdMageScar
from commands.exceptions import CommandError
from world.conditions.factories import DamageTypeFactory
from world.magic.constants import PendingAlterationStatus
from world.magic.factories import (
    CharacterSheetFactory,
    MagicalAlterationTemplateFactory,
    PendingAlterationFactory,
)


class CmdMageScarParseTests(TestCase):
    def _cmd(self) -> CmdMageScar:
        return CmdMageScar()

    def test_parse_kwargs_empty(self) -> None:
        assert self._cmd()._parse_kwargs([]) == {}

    def test_parse_kwargs_basic(self) -> None:
        result = self._cmd()._parse_kwargs(["name=Foo", "player=Bar"])
        assert result == {"name": "Foo", "player": "Bar"}

    def test_parse_kwargs_lowercases_keys(self) -> None:
        result = self._cmd()._parse_kwargs(["Name=Foo", "PLAYER=Bar"])
        assert result == {"name": "Foo", "player": "Bar"}

    def test_parse_kwargs_rejects_missing_key(self) -> None:
        with self.assertRaisesMessage(CommandError, "Invalid argument '=Foo'"):
            self._cmd()._parse_kwargs(["=Foo"])

    def test_parse_kwargs_rejects_no_equals(self) -> None:
        with self.assertRaisesMessage(CommandError, "Invalid argument 'Foo'"):
            self._cmd()._parse_kwargs(["Foo"])


class CmdMageScarScratchKwargsTests(TestCase):
    def _cmd(self) -> CmdMageScar:
        return CmdMageScar()

    @classmethod
    def setUpTestData(cls) -> None:
        cls.damage_type = DamageTypeFactory(name="fire")
        cls.parent_template = MagicalAlterationTemplateFactory()

    def test_required_fields_only(self) -> None:
        result = self._cmd()._build_scratch_kwargs(
            {"name": "Scar", "player": "pdesc", "observer": "odesc"}
        )
        assert result["name"] == "Scar"
        assert result["player_description"] == "pdesc"
        assert result["observer_description"] == "odesc"
        assert result["weakness_damage_type"] is None
        assert result["parent_template"] is None
        assert result["weakness_magnitude"] == 0
        assert result["resonance_bonus_magnitude"] == 0
        assert result["social_reactivity_magnitude"] == 0
        assert result["is_visible_at_rest"] is False

    def test_all_optional_fields(self) -> None:
        result = self._cmd()._build_scratch_kwargs(
            {
                "name": "Scar",
                "player": "pdesc",
                "observer": "odesc",
                "weakness": "fire",
                "weak_mag": "2",
                "res_mag": "3",
                "social_mag": "1",
                "visible": "yes",
                "parent": str(self.parent_template.pk),
            }
        )
        assert result["weakness_damage_type"] == self.damage_type
        assert result["weakness_magnitude"] == 2
        assert result["resonance_bonus_magnitude"] == 3
        assert result["social_reactivity_magnitude"] == 1
        assert result["is_visible_at_rest"] is True
        assert result["parent_template"] == self.parent_template

    def test_weakness_resolves_by_id(self) -> None:
        result = self._cmd()._build_scratch_kwargs(
            {
                "name": "Scar",
                "player": "pdesc",
                "observer": "odesc",
                "weakness": str(self.damage_type.pk),
            }
        )
        assert result["weakness_damage_type"] == self.damage_type

    def test_missing_required_fields(self) -> None:
        with self.assertRaisesMessage(
            CommandError, "Missing scratch fields: name, observer, player"
        ):
            self._cmd()._build_scratch_kwargs({})

    def test_unknown_weakness(self) -> None:
        with self.assertRaisesMessage(CommandError, "Damage type 'void' was not found."):
            self._cmd()._build_scratch_kwargs(
                {
                    "name": "Scar",
                    "player": "pdesc",
                    "observer": "odesc",
                    "weakness": "void",
                }
            )

    def test_invalid_weak_mag(self) -> None:
        with self.assertRaisesMessage(CommandError, "weak_mag must be a number."):
            self._cmd()._build_scratch_kwargs(
                {
                    "name": "Scar",
                    "player": "pdesc",
                    "observer": "odesc",
                    "weak_mag": "x",
                }
            )

    def test_parent_not_found(self) -> None:
        with self.assertRaisesMessage(CommandError, "Parent template id was not found."):
            self._cmd()._build_scratch_kwargs(
                {
                    "name": "Scar",
                    "player": "pdesc",
                    "observer": "odesc",
                    "parent": "99999",
                }
            )


class CmdMageScarListTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.other_sheet = CharacterSheetFactory()
        cls.character = cast(Any, cls.sheet.character)
        cls.character.msg = MagicMock()

    def _cmd(self) -> CmdMageScar:
        cmd = CmdMageScar()
        cmd.caller = self.character
        return cmd

    def test_no_pending_alterations(self) -> None:
        self._cmd()._handle_list()
        self.character.msg.assert_called_once_with("You have no pending Mage Scars.")

    def test_lists_open_pending_alterations(self) -> None:
        pending = PendingAlterationFactory(
            character=self.sheet, status=PendingAlterationStatus.OPEN
        )
        self._cmd()._handle_list()
        call_text = self.character.msg.call_args[0][0]
        assert "Pending Mage Scars" in call_text
        assert f"[#{pending.pk}]" in call_text
        assert pending.origin_affinity.name in call_text
        assert pending.origin_resonance.name in call_text

    def test_lists_only_open_for_caller(self) -> None:
        PendingAlterationFactory(character=self.sheet, status=PendingAlterationStatus.RESOLVED)
        PendingAlterationFactory(character=self.other_sheet, status=PendingAlterationStatus.OPEN)
        self._cmd()._handle_list()
        self.character.msg.assert_called_once_with("You have no pending Mage Scars.")


class CmdMageScarResolveTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.character = cast(Any, cls.sheet.character)
        cls.character.msg = MagicMock()
        cls.pending = PendingAlterationFactory(
            character=cls.sheet, status=PendingAlterationStatus.OPEN
        )
        cls.damage_type = DamageTypeFactory(name="fire")
        cls.parent_template = MagicalAlterationTemplateFactory()

    def _cmd(self) -> CmdMageScar:
        cmd = CmdMageScar()
        cmd.caller = self.character
        return cmd

    def test_library_resolve(self) -> None:
        library_template = MagicalAlterationTemplateFactory(is_library_entry=True)
        cmd = self._cmd()
        result = ActionResult(success=True, message="Resolved from library.")
        with patch.object(cmd.action, "run", return_value=result) as mock_run:
            cmd._handle_resolve(f"{self.pending.pk} template={library_template.pk}")

            mock_run.assert_called_once()
            call_kwargs = mock_run.call_args.kwargs
            assert call_kwargs["actor"] == self.character
            assert call_kwargs["pending_id"] == self.pending.pk
            assert call_kwargs["library_template_id"] == library_template.pk
        self.character.msg.assert_called_once_with("Resolved from library.")

    def test_scratch_resolve(self) -> None:
        cmd = self._cmd()
        result = ActionResult(success=True, message="Resolved from scratch.")
        with patch.object(cmd.action, "run", return_value=result) as mock_run:
            cmd._handle_resolve(
                f"{self.pending.pk} name=MyScar player=playerdesc observer=observerdesc"
            )

            call_kwargs = mock_run.call_args.kwargs
            assert call_kwargs["pending_id"] == self.pending.pk
            assert call_kwargs["name"] == "MyScar"
            assert call_kwargs["player_description"] == "playerdesc"
            assert call_kwargs["observer_description"] == "observerdesc"
            assert call_kwargs["weakness_damage_type"] is None
        self.character.msg.assert_called_once_with("Resolved from scratch.")

    def test_scratch_resolve_with_optional_scratch_keyword(self) -> None:
        cmd = self._cmd()
        result = ActionResult(success=True, message="OK")
        with patch.object(cmd.action, "run", return_value=result) as mock_run:
            cmd._handle_resolve(
                f"{self.pending.pk} scratch name=Scar player=p observer=o "
                f"weakness=fire weak_mag=1 res_mag=2 social_mag=3 visible=yes "
                f"parent={self.parent_template.pk}"
            )

            call_kwargs = mock_run.call_args.kwargs
            assert call_kwargs["pending_id"] == self.pending.pk
            assert call_kwargs["name"] == "Scar"
            assert call_kwargs["weakness_damage_type"] == self.damage_type
            assert call_kwargs["weakness_magnitude"] == 1
            assert call_kwargs["resonance_bonus_magnitude"] == 2
            assert call_kwargs["social_reactivity_magnitude"] == 3
            assert call_kwargs["is_visible_at_rest"] is True
            assert call_kwargs["parent_template"] == self.parent_template
        self.character.msg.assert_called_once_with("OK")

    def test_resolve_requires_pending_id(self) -> None:
        with self.assertRaisesMessage(CommandError, "Resolve which pending alteration?"):
            self._cmd()._handle_resolve("")

    def test_resolve_pending_id_must_be_number(self) -> None:
        with self.assertRaisesMessage(CommandError, "Pending alteration id must be a number."):
            self._cmd()._handle_resolve("abc template=1")

    def test_library_template_id_must_be_number(self) -> None:
        cmd = self._cmd()
        with self.assertRaisesMessage(CommandError, "Library template id must be a number."):
            cmd._handle_resolve(f"{self.pending.pk} template=abc")


class CmdMageScarFuncTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.character = cast(Any, cls.sheet.character)
        cls.character.msg = MagicMock()

    def _cmd(self, args: str) -> CmdMageScar:
        cmd = CmdMageScar()
        cmd.caller = self.character
        cmd.args = args
        cmd.raw_string = f"magescar {args}"
        return cmd

    def test_bare_command_lists_pending(self) -> None:
        self._cmd("").func()
        self.character.msg.assert_called_once_with("You have no pending Mage Scars.")

    def test_list_subcommand_lists_pending(self) -> None:
        self._cmd("list").func()
        self.character.msg.assert_called_once_with("You have no pending Mage Scars.")

    def test_resolve_subcommand(self) -> None:
        pending = PendingAlterationFactory(
            character=self.sheet, status=PendingAlterationStatus.OPEN
        )
        cmd = self._cmd(f"resolve {pending.pk} template=1")
        result = ActionResult(success=True, message="Resolved from tests.")
        with patch.object(cmd.action, "run", return_value=result) as mock_run:
            cmd.func()
            mock_run.assert_called_once()

    def test_invalid_subcommand_reports_usage(self) -> None:
        self._cmd("frobnicate").func()
        call_text = self.character.msg.call_args[0][0]
        assert "Usage: magescar [list|resolve <id> ...]" in call_text
