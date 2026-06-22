"""Tests for WeaveThreadAction — the action.run() seam over weave_thread (#1337)."""

from __future__ import annotations

from django.test import TestCase

from actions.definitions.threads import WeaveThreadAction
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import TargetKind
from world.magic.factories import (
    CharacterThreadWeavingUnlockFactory,
    ResonanceFactory,
    ThreadWeavingUnlockFactory,
)
from world.traits.factories import TraitFactory


class WeaveThreadActionTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory()
        cls.trait = TraitFactory()
        unlock = ThreadWeavingUnlockFactory(target_kind=TargetKind.TRAIT, unlock_trait=cls.trait)
        CharacterThreadWeavingUnlockFactory(character=cls.sheet, unlock=unlock, xp_spent=100)

    def test_run_creates_thread_and_returns_it_in_data(self) -> None:
        action = WeaveThreadAction()
        result = action.run(
            actor=self.sheet.character,
            target_kind=TargetKind.TRAIT,
            target=self.trait,
            resonance=self.resonance,
            name="Test Weave",
        )
        self.assertTrue(result.success, result.message)
        thread = result.data["thread"]
        self.assertEqual(thread.owner, self.sheet)
        self.assertEqual(thread.resonance, self.resonance)

    def test_run_returns_failure_when_unlock_missing(self) -> None:
        other_sheet = CharacterSheetFactory()
        action = WeaveThreadAction()
        result = action.run(
            actor=other_sheet.character,
            target_kind=TargetKind.TRAIT,
            target=self.trait,
            resonance=self.resonance,
        )
        self.assertFalse(result.success)
        self.assertTrue(result.message)
