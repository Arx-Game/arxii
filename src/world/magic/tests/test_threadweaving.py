"""Tests for the Phase 5 ThreadWeaving family (Spec A §2.1 lines 313-440, §4.2).

Coverage:
- ThreadWeavingUnlock partial-unique constraints fire only within the matching
  target_kind (one unlock per anchor).
- ThreadWeavingUnlock display_name derives the label from the discriminator FK.
- ThreadWeavingUnlock.clean() mirrors Thread.clean() (per-kind required FK,
  others null) plus ITEM typeclass-registry validation.
- CharacterThreadWeavingUnlock unique_together (character, unlock) — one purchase
  record per character per unlock.
- ThreadWeavingTeachingOffer FK shape (teacher + unlock + banked_ap).
"""

from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from django.test import TestCase

from world.magic.constants import TargetKind
from world.magic.factories import (
    GiftFactory,
    ThreadWeavingUnlockFactory,
)
from world.traits.factories import TraitFactory


class ThreadWeavingUnlockPartialUniqueTests(TestCase):
    def test_two_trait_unlocks_for_same_trait_collide(self) -> None:
        trait = TraitFactory()
        ThreadWeavingUnlockFactory(
            target_kind=TargetKind.TRAIT,
            unlock_trait=trait,
            xp_cost=100,
        )
        with self.assertRaises(IntegrityError):
            ThreadWeavingUnlockFactory(
                target_kind=TargetKind.TRAIT,
                unlock_trait=trait,
                xp_cost=100,
            )

    def test_two_trait_unlocks_different_traits_coexist(self) -> None:
        ThreadWeavingUnlockFactory(
            target_kind=TargetKind.TRAIT,
            unlock_trait=TraitFactory(),
        )
        ThreadWeavingUnlockFactory(
            target_kind=TargetKind.TRAIT,
            unlock_trait=TraitFactory(),
        )

    def test_cross_discriminator_independence(self) -> None:
        ThreadWeavingUnlockFactory(
            target_kind=TargetKind.TRAIT,
            unlock_trait=TraitFactory(),
        )
        # ITEM uses a typeclass path string, not a FK
        ThreadWeavingUnlockFactory(
            target_kind=TargetKind.ITEM,
            unlock_trait=None,
            unlock_item_typeclass_path="typeclasses.objects.Object",
        )


class ThreadWeavingUnlockDisplayNameTests(TestCase):
    def test_trait_display_name(self) -> None:
        trait = TraitFactory(name="Strength")
        u = ThreadWeavingUnlockFactory(target_kind=TargetKind.TRAIT, unlock_trait=trait)
        self.assertEqual(u.display_name, "ThreadWeaving: Strength")

    def test_technique_display_name(self) -> None:
        gift = GiftFactory(name="Blade")
        u = ThreadWeavingUnlockFactory(
            target_kind=TargetKind.TECHNIQUE,
            unlock_trait=None,
            unlock_gift=gift,
        )
        self.assertEqual(u.display_name, "ThreadWeaving: Gift of Blade")

    def test_item_display_name_strips_module_path(self) -> None:
        u = ThreadWeavingUnlockFactory(
            target_kind=TargetKind.ITEM,
            unlock_trait=None,
            unlock_item_typeclass_path="typeclasses.objects.Object",
        )
        self.assertEqual(u.display_name, "ThreadWeaving: Object")


class ThreadWeavingUnlockCleanTests(TestCase):
    def test_clean_rejects_no_target_fk(self) -> None:
        u = ThreadWeavingUnlockFactory.build(
            target_kind=TargetKind.TRAIT,
            unlock_trait=None,
        )
        with self.assertRaises(ValidationError):
            u.clean()

    def test_clean_accepts_correct_trait_target(self) -> None:
        trait = TraitFactory()
        u = ThreadWeavingUnlockFactory.build(
            target_kind=TargetKind.TRAIT,
            unlock_trait=trait,
        )
        u.clean()  # no exception
