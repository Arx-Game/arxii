"""Tests for CmdImbue — thin telnet shell over ImbueAction (#1342)."""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from commands.imbue import CmdImbue
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterResonanceFactory,
    ImbuingRitualFactory,
    ThreadFactory,
)
from world.magic.models import PendingRitualEffect


class CmdImbueTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.cr = CharacterResonanceFactory(character_sheet=cls.sheet, balance=100)
        cls.resonance = cls.cr.resonance
        cls.thread = ThreadFactory(owner=cls.sheet, resonance=cls.resonance, name="Ember Thread")
        cls.ritual = ImbuingRitualFactory()

    def setUp(self) -> None:
        self.character = self.sheet.character
        self.character.msg = MagicMock()
        CharacterAnimaFactory(character=self.character)
        # Each test needs a fresh PendingRitualEffect since the action consumes it.
        PendingRitualEffect.objects.get_or_create(character=self.sheet, ritual=self.ritual)

    def _make_cmd(self, args: str) -> CmdImbue:
        cmd = CmdImbue()
        cmd.caller = self.character
        cmd.args = args
        cmd.raw_string = f"imbue {args}"
        return cmd

    def test_imbue_fails_without_ceremony(self) -> None:
        """ImbueAction's prerequisite blocks imbuing without the pending effect."""
        from actions.definitions.imbue import ImbueAction

        PendingRitualEffect.objects.filter(character=self.sheet, ritual=self.ritual).delete()
        result = ImbueAction().run(
            actor=self.character,
            thread=self.thread,
            amount=1,
        )
        self.assertFalse(result.success)
        self.assertIn("Rite of Imbuing", result.message)

    def test_resolve_thread_by_name(self) -> None:
        """resolve_action_args returns the thread resolved by name."""
        cmd = self._make_cmd(f"thread={self.thread.name} amount=1")
        kwargs = cmd.resolve_action_args()
        self.assertEqual(kwargs["thread"], self.thread)
        self.assertEqual(kwargs["amount"], 1)

    def test_resolve_thread_by_pk(self) -> None:
        """resolve_action_args returns the thread resolved by primary key."""
        cmd = self._make_cmd(f"thread={self.thread.pk} amount=1")
        kwargs = cmd.resolve_action_args()
        self.assertEqual(kwargs["thread"], self.thread)
        self.assertEqual(kwargs["amount"], 1)

    def test_thread_name_with_spaces(self) -> None:
        """Thread names containing spaces are parsed correctly."""
        self.thread.name = "Ember of Endurance"
        self.thread.save()
        cmd = self._make_cmd("thread=Ember of Endurance amount=5")
        kwargs = cmd.resolve_action_args()
        self.assertEqual(kwargs["thread"], self.thread)
        self.assertEqual(kwargs["amount"], 5)

    def test_missing_thread_reports_error(self) -> None:
        """Missing thread= kwarg sends an error to the caller."""
        cmd = self._make_cmd("amount=1")
        cmd.func()
        self.character.msg.assert_called()

    def test_missing_amount_reports_error(self) -> None:
        """Missing amount= kwarg sends an error to the caller."""
        cmd = self._make_cmd(f"thread={self.thread.pk}")
        cmd.func()
        self.character.msg.assert_called()

    def test_unknown_thread_reports_error(self) -> None:
        """An unrecognised thread value sends an error to the caller."""
        cmd = self._make_cmd("thread=99999 amount=1")
        cmd.func()
        self.character.msg.assert_called()
