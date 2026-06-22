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
    WeavingCeremonyFactory,
)
from world.magic.models import PendingRitualEffect
from world.traits.factories import TraitFactory


class WeaveThreadActionTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory()
        cls.trait = TraitFactory()
        unlock = ThreadWeavingUnlockFactory(target_kind=TargetKind.TRAIT, unlock_trait=cls.trait)
        CharacterThreadWeavingUnlockFactory(character=cls.sheet, unlock=unlock, xp_spent=100)
        cls.weaving_ritual = WeavingCeremonyFactory()

    def setUp(self) -> None:
        # Each test needs a fresh PendingRitualEffect since the action consumes it.
        PendingRitualEffect.objects.get_or_create(character=self.sheet, ritual=self.weaving_ritual)

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

    def test_run_consumes_pending_effect_on_success(self) -> None:
        action = WeaveThreadAction()
        self.assertTrue(
            PendingRitualEffect.objects.filter(
                character=self.sheet, ritual=self.weaving_ritual
            ).exists()
        )
        result = action.run(
            actor=self.sheet.character,
            target_kind=TargetKind.TRAIT,
            target=self.trait,
            resonance=self.resonance,
        )
        self.assertTrue(result.success, result.message)
        self.assertFalse(
            PendingRitualEffect.objects.filter(
                character=self.sheet, ritual=self.weaving_ritual
            ).exists()
        )

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

    def test_run_returns_failure_without_pending_effect(self) -> None:
        PendingRitualEffect.objects.filter(
            character=self.sheet, ritual=self.weaving_ritual
        ).delete()
        action = WeaveThreadAction()
        result = action.run(
            actor=self.sheet.character,
            target_kind=TargetKind.TRAIT,
            target=self.trait,
            resonance=self.resonance,
        )
        self.assertFalse(result.success)
        self.assertIn("Rite of Weaving", result.message)
