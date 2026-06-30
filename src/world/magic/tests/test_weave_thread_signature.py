"""Tests for the #1582 carry-forward fixes in weave_thread.

(a) Cache invalidation: weaving a TECHNIQUE-kind thread calls
    character.threads.invalidate() so the newly-created thread is
    immediately visible in the next character.threads.all() call.

(b) Ownership guard: weaving a TECHNIQUE-kind thread on a technique the
    character does not know raises TechniqueNotOwned.
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import TargetKind
from world.magic.exceptions import TechniqueNotOwned
from world.magic.factories import (
    CharacterTechniqueFactory,
    CharacterThreadWeavingUnlockFactory,
    GiftFactory,
    ResonanceFactory,
    TechniqueFactory,
    ThreadWeavingUnlockFactory,
)
from world.magic.services.threads import weave_thread


def _setup_technique_weave_unlock(sheet, gift):
    """Create a TECHNIQUE ThreadWeavingUnlock + CharacterThreadWeavingUnlock for sheet."""
    unlock = ThreadWeavingUnlockFactory(
        target_kind=TargetKind.TECHNIQUE,
        unlock_trait=None,
        unlock_gift=gift,
        xp_cost=0,
    )
    CharacterThreadWeavingUnlockFactory(character=sheet, unlock=unlock, xp_spent=0)
    return unlock


class WeaveTechniqueThreadCacheInvalidationTests(TestCase):
    """weave_thread for a TECHNIQUE target invalidates the threads cache on success."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory()
        cls.gift = GiftFactory()
        cls.technique = TechniqueFactory(gift=cls.gift, level=1, damage_profile=False)
        # Character knows this technique.
        CharacterTechniqueFactory(character=cls.sheet, technique=cls.technique)
        # Character has the weaving unlock covering the gift.
        _setup_technique_weave_unlock(cls.sheet, cls.gift)

    def test_new_thread_visible_after_cache_was_warm(self) -> None:
        """Thread created by weave_thread appears in character.threads.all().

        This test warms the cache before the weave call. If weave_thread does
        NOT invalidate, character.threads.all() would return the old stale list
        that lacks the newly-woven thread.
        """
        character = self.sheet.character
        # Warm the threads cache (empty at this point).
        threads_before = character.threads.all()
        self.assertEqual(len(threads_before), 0, "pre-condition: no threads yet")

        thread = weave_thread(
            self.sheet,
            target_kind=TargetKind.TECHNIQUE,
            target=self.technique,
            resonance=self.resonance,
        )

        # After weave_thread, the cache must have been invalidated so that the
        # freshly-created thread is visible on the next read.
        threads_after = character.threads.all()
        self.assertIn(thread, threads_after)

    def test_weave_returns_a_thread_with_correct_kind(self) -> None:
        """Sanity check: weave_thread creates a TECHNIQUE-kind Thread."""
        # Create a second technique so each test gets a unique anchor.
        technique2 = TechniqueFactory(gift=self.gift, level=2, damage_profile=False)
        CharacterTechniqueFactory(character=self.sheet, technique=technique2)

        thread = weave_thread(
            self.sheet,
            target_kind=TargetKind.TECHNIQUE,
            target=technique2,
            resonance=self.resonance,
        )
        self.assertEqual(thread.target_kind, TargetKind.TECHNIQUE)
        self.assertEqual(thread.target_technique_id, technique2.pk)
        self.assertEqual(thread.owner_id, self.sheet.pk)


class WeaveTechniqueThreadOwnershipGuardTests(TestCase):
    """weave_thread raises TechniqueNotOwned when the character lacks the technique."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory()
        cls.gift = GiftFactory()
        cls.technique = TechniqueFactory(gift=cls.gift, level=1, damage_profile=False)
        # Deliberately do NOT create a CharacterTechnique for cls.sheet.
        # Character still has the weaving unlock so the WeavingUnlockMissing
        # guard passes first; TechniqueNotOwned fires in the new guard.
        _setup_technique_weave_unlock(cls.sheet, cls.gift)

    def test_raises_when_technique_not_known(self) -> None:
        """weave_thread raises TechniqueNotOwned when no CharacterTechnique exists."""
        with self.assertRaises(TechniqueNotOwned):
            weave_thread(
                self.sheet,
                target_kind=TargetKind.TECHNIQUE,
                target=self.technique,
                resonance=self.resonance,
            )

    def test_known_technique_does_not_raise(self) -> None:
        """weave_thread does NOT raise TechniqueNotOwned when the technique IS known."""
        # Grant the technique first.
        CharacterTechniqueFactory(character=self.sheet, technique=self.technique)
        # Should not raise.
        thread = weave_thread(
            self.sheet,
            target_kind=TargetKind.TECHNIQUE,
            target=self.technique,
            resonance=self.resonance,
        )
        self.assertIsNotNone(thread)
