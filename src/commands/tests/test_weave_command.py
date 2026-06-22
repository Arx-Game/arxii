"""Tests for CmdWeaveThread — the thin telnet shell over WeaveThreadAction (#1337)."""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from commands.weave import CmdWeaveThread
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import TargetKind
from world.magic.factories import (
    CharacterThreadWeavingUnlockFactory,
    ResonanceFactory,
    ThreadWeavingUnlockFactory,
)
from world.magic.models import Thread
from world.traits.factories import TraitFactory


class CmdWeaveThreadTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory(name="Embers")
        cls.trait = TraitFactory()
        unlock = ThreadWeavingUnlockFactory(target_kind=TargetKind.TRAIT, unlock_trait=cls.trait)
        CharacterThreadWeavingUnlockFactory(character=cls.sheet, unlock=unlock, xp_spent=100)

    def setUp(self) -> None:
        self.character = self.sheet.character
        self.character.msg = MagicMock()

    def _run(self, args: str) -> None:
        cmd = CmdWeaveThread()
        cmd.caller = self.character
        cmd.args = args
        cmd.raw_string = f"weave {args}"
        cmd.func()

    def test_weave_creates_thread(self) -> None:
        self._run(f"resonance=Embers trait={self.trait.pk}")
        self.assertTrue(Thread.objects.filter(owner=self.sheet, resonance=self.resonance).exists())
        self.character.msg.assert_called()

    def test_weave_passes_optional_name(self) -> None:
        self._run(f"resonance=Embers trait={self.trait.pk} name=My Bright Thread")
        thread = Thread.objects.get(owner=self.sheet, resonance=self.resonance)
        self.assertEqual(thread.name, "My Bright Thread")

    def test_unknown_resonance_reports_error(self) -> None:
        self._run(f"resonance=Nope trait={self.trait.pk}")
        self.assertFalse(Thread.objects.filter(owner=self.sheet).exists())
        self.character.msg.assert_called()

    def test_missing_trait_reports_error(self) -> None:
        self._run("resonance=Embers")
        self.assertFalse(Thread.objects.filter(owner=self.sheet).exists())
        self.character.msg.assert_called()

    def test_unknown_trait_reports_error(self) -> None:
        self._run("resonance=Embers trait=99999")
        self.assertFalse(Thread.objects.filter(owner=self.sheet).exists())
        self.character.msg.assert_called()
