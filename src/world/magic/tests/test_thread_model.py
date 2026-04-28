"""Tests for the Phase 4 Thread model (discriminator + typed-FK pattern).

Spec A §2.1 lines 83-151 — Thread is per-character, anchored to a trait,
technique, item, room, relationship-track, or relationship-capstone via
exactly one populated target_* FK matching the target_kind discriminator.

Coverage:
- Field shape and defaults via factory.
- clean() rejects missing target_* and wrong-target-for-kind, accepts correct combos.
- Per-kind partial UniqueConstraints fire only within the same target_kind, so two
  threads for the same ObjectDB but different kinds (ITEM vs ROOM) can coexist.
- ThreadLevelUnlock unique-together (thread, unlocked_level) and multi-level coexistence.
"""

from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from django.test import TestCase
from evennia.utils import create

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import TargetKind
from world.magic.factories import (
    FacetFactory,
    ResonanceFactory,
    ThreadFactory,
    ThreadLevelUnlockFactory,
)
from world.magic.models import Thread
from world.traits.factories import TraitFactory


class ThreadModelShapeTests(TestCase):
    def test_thread_has_owner_resonance_target_kind_level_developed_points(self) -> None:
        thread = ThreadFactory()
        self.assertIsNotNone(thread.owner)
        self.assertIsNotNone(thread.resonance)
        self.assertEqual(thread.target_kind, TargetKind.TRAIT)
        self.assertEqual(thread.level, 0)
        self.assertEqual(thread.developed_points, 0)


class ThreadCleanTests(TestCase):
    def test_clean_rejects_no_target_fk(self) -> None:
        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        thread = Thread(
            owner=sheet,
            resonance=res,
            target_kind=TargetKind.TRAIT,
        )
        with self.assertRaises(ValidationError):
            thread.clean()

    def test_clean_rejects_wrong_target_fk_for_kind(self) -> None:
        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        trait = TraitFactory()
        thread = Thread(
            owner=sheet,
            resonance=res,
            target_kind=TargetKind.TECHNIQUE,
            target_trait=trait,  # wrong column for TECHNIQUE
        )
        with self.assertRaises(ValidationError):
            thread.clean()

    def test_clean_accepts_correct_target_fk(self) -> None:
        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        trait = TraitFactory()
        thread = Thread(
            owner=sheet,
            resonance=res,
            target_kind=TargetKind.TRAIT,
            target_trait=trait,
        )
        thread.clean()  # no exception

    def test_clean_rejects_item_not_in_registry(self) -> None:
        """ITEM-kind threads validate target_object.db_typeclass_path against the
        THREADWEAVING_ITEM_TYPECLASSES registry. Phase 1 left it empty, so any
        item must be rejected at this layer."""
        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        obj = create.create_object(
            typeclass="typeclasses.objects.Object",
            key="unregistered-item",
            nohome=True,
        )
        thread = Thread(
            owner=sheet,
            resonance=res,
            target_kind=TargetKind.ITEM,
            target_object=obj,
        )
        with self.assertRaises(ValidationError):
            thread.clean()


class ThreadPartialUniqueTests(TestCase):
    def test_two_trait_threads_same_owner_same_trait_same_resonance_collide(self) -> None:
        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        trait = TraitFactory()
        ThreadFactory(
            owner=sheet,
            resonance=res,
            target_kind=TargetKind.TRAIT,
            target_trait=trait,
        )
        with self.assertRaises(IntegrityError):
            ThreadFactory(
                owner=sheet,
                resonance=res,
                target_kind=TargetKind.TRAIT,
                target_trait=trait,
            )

    def test_two_threads_different_target_kind_same_object_coexist(self) -> None:
        """Same target_object FK (ObjectDB) but different discriminator —
        partial uniques don't collide."""
        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        obj = create.create_object(
            typeclass="typeclasses.objects.Object",
            key="test-anchor",
            nohome=True,
        )
        ThreadFactory(
            owner=sheet,
            resonance=res,
            target_kind=TargetKind.ITEM,
            target_object=obj,
            target_trait=None,  # explicitly null factory's default TRAIT FK
        )
        # ROOM thread on the same object — same target_object, different
        # target_kind — should NOT collide.
        ThreadFactory(
            owner=sheet,
            resonance=res,
            target_kind=TargetKind.ROOM,
            target_object=obj,
            target_trait=None,
        )


class ThreadLevelUnlockTests(TestCase):
    def test_same_thread_same_level_collides(self) -> None:
        thread = ThreadFactory()
        ThreadLevelUnlockFactory(thread=thread, unlocked_level=20, xp_spent=200)
        with self.assertRaises(IntegrityError):
            ThreadLevelUnlockFactory(thread=thread, unlocked_level=20, xp_spent=200)

    def test_different_levels_coexist(self) -> None:
        thread = ThreadFactory()
        ThreadLevelUnlockFactory(thread=thread, unlocked_level=20)
        ThreadLevelUnlockFactory(thread=thread, unlocked_level=30)
        self.assertEqual(thread.level_unlocks.count(), 2)


class ThreadFacetKindTests(TestCase):
    """Tests for the FACET TargetKind and target_facet typed FK (Spec D Task 9)."""

    def test_create_facet_thread(self) -> None:
        sheet = CharacterSheetFactory()
        facet = FacetFactory()
        res = ResonanceFactory()
        thread = Thread.objects.create(
            owner=sheet,
            target_kind=TargetKind.FACET,
            target_facet=facet,
            resonance=res,
            level=0,
        )
        self.assertEqual(thread.target_kind, TargetKind.FACET)
        self.assertEqual(thread.target_facet, facet)

    def test_target_property_returns_facet(self) -> None:
        sheet = CharacterSheetFactory()
        facet = FacetFactory()
        res = ResonanceFactory()
        thread = Thread.objects.create(
            owner=sheet,
            target_kind=TargetKind.FACET,
            target_facet=facet,
            resonance=res,
        )
        self.assertEqual(thread.target, facet)

    def test_clean_accepts_facet_kind_with_target_facet(self) -> None:
        sheet = CharacterSheetFactory()
        facet = FacetFactory()
        res = ResonanceFactory()
        thread = Thread(
            owner=sheet,
            resonance=res,
            target_kind=TargetKind.FACET,
            target_facet=facet,
        )
        thread.clean()  # no exception

    def test_clean_rejects_facet_kind_without_target_facet(self) -> None:
        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        thread = Thread(
            owner=sheet,
            resonance=res,
            target_kind=TargetKind.FACET,
        )
        with self.assertRaises(ValidationError):
            thread.clean()

    def test_facet_kind_requires_only_target_facet(self) -> None:
        """Setting any other typed FK alongside target_facet with kind=FACET must fail."""
        sheet = CharacterSheetFactory()
        trait = TraitFactory()
        with self.assertRaises(IntegrityError):
            Thread.objects.create(
                owner=sheet,
                target_kind=TargetKind.FACET,
                target_facet=FacetFactory(),
                target_trait=trait,
                resonance=ResonanceFactory(),
            )

    def test_facet_thread_unique_per_owner_resonance_facet(self) -> None:
        sheet = CharacterSheetFactory()
        facet = FacetFactory()
        res = ResonanceFactory()
        Thread.objects.create(
            owner=sheet,
            target_kind=TargetKind.FACET,
            target_facet=facet,
            resonance=res,
        )
        with self.assertRaises(IntegrityError):
            Thread.objects.create(
                owner=sheet,
                target_kind=TargetKind.FACET,
                target_facet=facet,
                resonance=res,
            )
