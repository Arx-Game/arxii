"""Tests for the Phase 5 ThreadWeaving family (Spec A §2.1 lines 313-440, §4.2).

Coverage:
- ThreadWeavingUnlock partial-unique constraints fire only within the matching
  target_kind (one unlock per anchor).
- ThreadWeavingUnlock display_name derives the label from the discriminator FK.
- ThreadWeavingUnlock.clean() mirrors Thread.clean() (per-kind required FK,
  others null).
- CharacterThreadWeavingUnlock unique_together (character, unlock) — one purchase
  record per character per unlock.
- ThreadWeavingTeachingOffer FK shape (teacher + unlock + banked_ap).
"""

from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from django.test import TestCase

from world.magic.constants import TargetKind
from world.magic.factories import (
    CharacterThreadWeavingUnlockFactory,
    GiftFactory,
    ThreadWeavingTeachingOfferFactory,
    ThreadWeavingUnlockFactory,
)
from world.magic.models import ThreadWeavingUnlock
from world.relationships.factories import RelationshipTrackFactory
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
        # A different discriminator (RELATIONSHIP_TRACK) coexists with the TRAIT unlock.
        ThreadWeavingUnlockFactory(
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            unlock_trait=None,
            unlock_track=RelationshipTrackFactory(name="Consecrated"),
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

    def test_relationship_track_display_name(self) -> None:
        track = RelationshipTrackFactory(name="Romantic")
        u = ThreadWeavingUnlockFactory(
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            unlock_trait=None,
            unlock_track=track,
        )
        self.assertEqual(u.display_name, "ThreadWeaving: Romantic bonds")


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

    def test_db_rejects_capstone_target_kind(self) -> None:
        """CAPSTONE has no slot on this model — DB must reject it directly."""
        with self.assertRaises(IntegrityError):
            ThreadWeavingUnlock.objects.create(
                target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
                xp_cost=100,
            )


class KindLevelUnlockCleanTests(TestCase):
    """Kind-level unlocks (FACET, SANCTUM, ORGANIZATION) need no typed FK.

    All typed FKs must be null. clean() must accept these instead of raising
    'Unknown target_kind' (the pre-existing FACET gap this fixes).
    """

    def test_facet_unlock_passes_clean(self) -> None:
        """FACET kind-level unlock (all FKs null) passes full_clean."""
        unlock = ThreadWeavingUnlock(
            target_kind=TargetKind.FACET,
            xp_cost=100,
        )
        unlock.full_clean()  # should not raise

    def test_sanctum_unlock_passes_clean(self) -> None:
        """SANCTUM kind-level unlock (all FKs null) passes full_clean."""
        unlock = ThreadWeavingUnlock(
            target_kind=TargetKind.SANCTUM,
            xp_cost=100,
        )
        unlock.full_clean()

    def test_organization_unlock_passes_clean(self) -> None:
        """ORGANIZATION kind-level unlock (all FKs null) passes full_clean."""
        unlock = ThreadWeavingUnlock(
            target_kind=TargetKind.ORGANIZATION,
            xp_cost=100,
        )
        unlock.full_clean()

    def test_kind_level_unlock_rejects_typed_fk(self) -> None:
        """A kind-level unlock with a typed FK set raises ValidationError."""
        trait = TraitFactory()
        unlock = ThreadWeavingUnlock(
            target_kind=TargetKind.FACET,
            xp_cost=100,
            unlock_trait=trait,
        )
        with self.assertRaises(ValidationError):
            unlock.full_clean()

    def test_facet_unlock_display_name(self) -> None:
        unlock = ThreadWeavingUnlock(
            target_kind=TargetKind.FACET,
            xp_cost=100,
        )
        self.assertEqual(unlock.display_name, "ThreadWeaving: Facets")

    def test_sanctum_unlock_display_name(self) -> None:
        unlock = ThreadWeavingUnlock(
            target_kind=TargetKind.SANCTUM,
            xp_cost=100,
        )
        self.assertEqual(unlock.display_name, "ThreadWeaving: Sanctums")

    def test_organization_unlock_display_name(self) -> None:
        unlock = ThreadWeavingUnlock(
            target_kind=TargetKind.ORGANIZATION,
            xp_cost=100,
        )
        self.assertEqual(unlock.display_name, "ThreadWeaving: Organizations")


class CharacterThreadWeavingUnlockTests(TestCase):
    def test_idempotency_one_purchase_per_unlock(self) -> None:
        unlock = ThreadWeavingUnlockFactory()
        purchase = CharacterThreadWeavingUnlockFactory(unlock=unlock, xp_spent=100)
        with self.assertRaises(IntegrityError):
            CharacterThreadWeavingUnlockFactory(
                character=purchase.character,
                unlock=unlock,
                xp_spent=100,
            )


class ThreadWeavingTeachingOfferTests(TestCase):
    def test_offer_links_teacher_and_unlock(self) -> None:
        offer = ThreadWeavingTeachingOfferFactory()
        self.assertIsNotNone(offer.teacher)
        self.assertIsNotNone(offer.unlock)
        self.assertGreaterEqual(offer.banked_ap, 0)
