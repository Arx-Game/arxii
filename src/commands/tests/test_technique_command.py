"""Tests for CmdTechnique — the staff technique-authoring workbench (#1496).

TDD coverage per the task brief:
- ``technique draft <name>`` starts a draft; ``technique show`` displays it.
- A non-staff caller is DENIED by the lock (perm check on the command).
- ``technique author`` on a complete draft creates a Technique.
"""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock

from django.test import TestCase

from commands.technique import CmdTechnique
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import EffectTypeFactory, GiftFactory, TechniqueStyleFactory
from world.magic.models import Technique, TechniqueDraft


class CmdTechniqueLockTests(TestCase):
    """The command declares perm(Builder) — verified via the locks string."""

    def test_command_is_builder_locked(self) -> None:
        cmd = CmdTechnique()
        assert "perm(Builder)" in cmd.locks


class CmdTechniqueDraftShowTests(TestCase):
    """``technique draft <name>`` creates a draft; ``technique show`` renders it."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()

    def setUp(self) -> None:
        self.character = cast(Any, self.sheet.character)
        self.character.msg = MagicMock()

    def _run(self, args: str) -> None:
        cmd = CmdTechnique()
        cmd.caller = self.character
        cmd.args = args
        cmd.raw_string = f"technique {args}"
        cmd.func()

    def test_draft_creates_technique_draft(self) -> None:
        self._run("draft Ember Strike")
        assert TechniqueDraft.objects.filter(character=self.sheet).exists()
        self.character.msg.assert_called()

    def test_draft_confirmation_message_mentions_name(self) -> None:
        self._run("draft Flame Bolt")
        output = "\n".join(str(c.args[0]) for c in self.character.msg.call_args_list if c.args)
        assert "Flame Bolt" in output

    def test_draft_without_name_reports_usage(self) -> None:
        self._run("draft")
        output = "\n".join(str(c.args[0]) for c in self.character.msg.call_args_list if c.args)
        assert "Usage" in output
        assert not TechniqueDraft.objects.filter(character=self.sheet).exists()

    def test_show_after_draft_displays_draft_name(self) -> None:
        self._run("draft Frost Spear")
        self.character.msg.reset_mock()
        self._run("show")
        output = "\n".join(str(c.args[0]) for c in self.character.msg.call_args_list if c.args)
        assert "Frost Spear" in output

    def test_show_without_draft_reports_friendly_error(self) -> None:
        # No draft started for this test — expect the NoActiveTechniqueDraft message.
        self._run("show")
        output = "\n".join(str(c.args[0]) for c in self.character.msg.call_args_list if c.args)
        assert "technique draft" in output.lower() or "no technique draft" in output.lower()

    def test_unknown_subcommand_shows_usage(self) -> None:
        self._run("frobnicate")
        output = "\n".join(str(c.args[0]) for c in self.character.msg.call_args_list if c.args)
        # The usage block always starts with "technique draft"
        assert "technique draft" in output.lower()

    def test_set_updates_name_field(self) -> None:
        self._run("draft Temp Name")
        self.character.msg.reset_mock()
        self._run("set name=Renamed Technique")
        draft = TechniqueDraft.objects.get(character=self.sheet)
        assert draft.name == "Renamed Technique"

    def test_discard_removes_draft(self) -> None:
        self._run("draft To Discard")
        assert TechniqueDraft.objects.filter(character=self.sheet).exists()
        self.character.msg.reset_mock()
        self._run("discard")
        assert not TechniqueDraft.objects.filter(character=self.sheet).exists()
        self.character.msg.assert_called()


class CmdTechniqueAuthorTests(TestCase):
    """``technique author`` on a complete draft creates a Technique (staff path)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.gift = GiftFactory(creator=cls.sheet)
        cls.style = TechniqueStyleFactory()
        cls.effect_type = EffectTypeFactory()

    def setUp(self) -> None:
        self.character = cast(Any, self.sheet.character)
        self.character.msg = MagicMock()
        # Build a complete draft so author can proceed without errors.
        self._build_complete_draft()

    def _build_complete_draft(self) -> None:
        from world.magic.services.technique_draft import set_draft_fields, start_technique_draft

        draft = start_technique_draft(self.sheet, name="Staff Technique")
        set_draft_fields(
            draft,
            gift=self.gift,
            style=self.style,
            effect_type=self.effect_type,
            action_category="physical",
            tier=1,
        )

    def _run(self, args: str) -> None:
        cmd = CmdTechnique()
        cmd.caller = self.character
        cmd.args = args
        cmd.raw_string = f"technique {args}"
        cmd.func()

    def test_author_creates_technique(self) -> None:
        count_before = Technique.objects.count()
        self._run("author")
        assert Technique.objects.count() == count_before + 1

    def test_author_emits_success_message(self) -> None:
        self._run("author")
        output = "\n".join(str(c.args[0]) for c in self.character.msg.call_args_list if c.args)
        # The action result message mentions the technique name.
        assert "Staff Technique" in output

    def test_author_discards_draft_on_success(self) -> None:
        self._run("author")
        assert not TechniqueDraft.objects.filter(character=self.sheet).exists()

    def test_author_on_incomplete_draft_reports_missing_fields(self) -> None:
        # Start a fresh incomplete draft (only name, no required FK fields).
        from world.magic.services.technique_draft import start_technique_draft

        start_technique_draft(self.sheet, name="Incomplete")
        self._run("author")
        output = "\n".join(str(c.args[0]) for c in self.character.msg.call_args_list if c.args)
        # TechniqueDraftIncomplete message mentions "missing" or the field names.
        assert "missing" in output.lower() or "incomplete" in output.lower()

    def test_price_shows_breakdown_for_complete_draft(self) -> None:
        self._run("price")
        output = "\n".join(str(c.args[0]) for c in self.character.msg.call_args_list if c.args)
        assert "Total:" in output or "total:" in output.lower()
        assert "budget" in output.lower()
