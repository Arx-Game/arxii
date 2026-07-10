"""Tests for WeaveThreadAction — the action.run() seam over weave_thread (#1337).

The happy-path weave (thread created + pending effect consumed) is covered by
the E2E journey test ``test_weave_imbue_pull_journey_e2e.py`` (Step 2). These
tests retain only the failure-path edge cases the journey does NOT cover:
missing unlock, missing pending effect, and unsupported GIFT resonance.
"""

from __future__ import annotations

from django.test import TestCase

from actions.definitions.threads import WeaveThreadAction
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import TargetKind
from world.magic.exceptions import UnsupportedGiftResonanceError
from world.magic.factories import (
    CharacterThreadWeavingUnlockFactory,
    GiftFactory,
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

    def test_run_returns_failure_for_unsupported_gift_resonance(self) -> None:
        # GIFT weaving sidesteps the unlock gate (the GIFT branch in weave_thread
        # runs before _has_weaving_unlock). An unsupported resonance raises
        # UnsupportedGiftResonanceError in the service; the action must catch it
        # and return a failure ActionResult rather than propagating a 500.
        gift = GiftFactory()
        supported = ResonanceFactory()
        gift.resonances.add(supported)
        unsupported = ResonanceFactory()
        action = WeaveThreadAction()
        result = action.run(
            actor=self.sheet.character,
            target_kind=TargetKind.GIFT,
            target=gift,
            resonance=unsupported,
        )
        self.assertFalse(result.success)
        self.assertEqual(result.message, UnsupportedGiftResonanceError.user_message)
