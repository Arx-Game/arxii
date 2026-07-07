"""Tests for CharacterWeavingUnlockHandler — cached weaving-unlock lookups (ADR-0093)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import TargetKind
from world.magic.models import CharacterThreadWeavingUnlock, ThreadWeavingUnlock
from world.traits.factories import TraitFactory


class CharacterWeavingUnlockHandlerTests(TestCase):
    def test_has_unlock_for_kind_true(self):
        """Handler returns True when the character has a kind-level unlock."""
        sheet = CharacterSheetFactory()
        unlock = ThreadWeavingUnlock.objects.create(
            target_kind=TargetKind.ORGANIZATION, xp_cost=100
        )
        CharacterThreadWeavingUnlock.objects.create(character=sheet, unlock=unlock, xp_spent=100)
        char = sheet.character
        self.assertTrue(char.weaving_unlocks.has_unlock_for_kind(TargetKind.ORGANIZATION))

    def test_has_unlock_for_kind_false(self):
        """Handler returns False when the character has no unlock of that kind."""
        sheet = CharacterSheetFactory()
        char = sheet.character
        self.assertFalse(char.weaving_unlocks.has_unlock_for_kind(TargetKind.ORGANIZATION))

    def test_has_unlock_for_trait_true(self):
        """Handler returns True for a TRAIT-kind unlock matching the trait."""
        sheet = CharacterSheetFactory()
        trait = TraitFactory()
        unlock = ThreadWeavingUnlock.objects.create(
            target_kind=TargetKind.TRAIT, xp_cost=100, unlock_trait=trait
        )
        CharacterThreadWeavingUnlock.objects.create(character=sheet, unlock=unlock, xp_spent=100)
        char = sheet.character
        self.assertTrue(char.weaving_unlocks.has_unlock_for_trait(trait))

    def test_has_unlock_for_trait_false_different_trait(self):
        """Handler returns False when the unlock is for a different trait."""
        sheet = CharacterSheetFactory()
        trait = TraitFactory()
        other_trait = TraitFactory()
        unlock = ThreadWeavingUnlock.objects.create(
            target_kind=TargetKind.TRAIT, xp_cost=100, unlock_trait=trait
        )
        CharacterThreadWeavingUnlock.objects.create(character=sheet, unlock=unlock, xp_spent=100)
        char = sheet.character
        self.assertFalse(char.weaving_unlocks.has_unlock_for_trait(other_trait))

    def test_invalidate_clears_cache(self):
        """After invalidation, a newly-added unlock is visible."""
        sheet = CharacterSheetFactory()
        char = sheet.character
        # Before any unlock: False
        self.assertFalse(char.weaving_unlocks.has_unlock_for_kind(TargetKind.ORGANIZATION))
        # Add unlock
        unlock = ThreadWeavingUnlock.objects.create(
            target_kind=TargetKind.ORGANIZATION, xp_cost=100
        )
        CharacterThreadWeavingUnlock.objects.create(character=sheet, unlock=unlock, xp_spent=100)
        # Cache is stale until invalidated
        char.weaving_unlocks.invalidate()
        self.assertTrue(char.weaving_unlocks.has_unlock_for_kind(TargetKind.ORGANIZATION))
