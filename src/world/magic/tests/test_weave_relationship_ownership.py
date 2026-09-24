"""Tests for the RELATIONSHIP_TRACK/RELATIONSHIP_CAPSTONE ownership assertion in
``weave_thread`` (#2033, #3957).

A character may only weave a thread anchored on their OWN
``CharacterRelationship`` side (or a ``RelationshipCapstone`` on their own
side) — never someone else's relationship, even when they hold a matching
``ThreadWeavingUnlock``. Before #2033, ``weave_thread`` checked the unlock
only; a character who happened to hold ANY RELATIONSHIP_TRACK unlock could
weave a thread anchored on ANY character's side.
"""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import TargetKind
from world.magic.exceptions import RelationshipBondNotOwned, RelationshipTierTooLow
from world.magic.factories import (
    CharacterThreadWeavingUnlockFactory,
    ResonanceFactory,
    ThreadWeavingUnlockFactory,
)
from world.magic.models import Thread
from world.magic.services import weave_thread
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipCapstoneFactory,
    RelationshipLabelFactory,
    RelationshipTypeFactory,
)


class RelationshipTrackOwnershipTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.other_sheet = CharacterSheetFactory()
        cls.partner_sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory()
        cls.rel_type = RelationshipTypeFactory()
        unlock = ThreadWeavingUnlockFactory(
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            unlock_trait=None,
            unlock_type=cls.rel_type,
        )
        # Both sheets hold the matching unlock — the unlock gate alone would let
        # either weave a RELATIONSHIP_TRACK thread; ownership must still gate it.
        CharacterThreadWeavingUnlockFactory(character=cls.sheet, unlock=unlock)
        CharacterThreadWeavingUnlockFactory(character=cls.other_sheet, unlock=unlock)

        cls.other_relationship = CharacterRelationshipFactory(
            source=cls.other_sheet, target=cls.partner_sheet
        )
        cls.other_relationship.tier = 2
        cls.other_relationship.invested_depth = 10
        cls.other_relationship.save()
        RelationshipLabelFactory(relationship=cls.other_relationship, type=cls.rel_type)

    def test_weaving_anothers_track_row_raises(self) -> None:
        pre_count = Thread.objects.filter(owner=self.sheet).count()
        with self.assertRaises(RelationshipBondNotOwned):
            weave_thread(
                character_sheet=self.sheet,
                target_kind=TargetKind.RELATIONSHIP_TRACK,
                target=self.other_relationship,
                resonance=self.resonance,
            )
        self.assertEqual(Thread.objects.filter(owner=self.sheet).count(), pre_count)

    def test_weaving_own_track_row_succeeds(self) -> None:
        own_relationship = CharacterRelationshipFactory(
            source=self.sheet, target=self.partner_sheet
        )
        own_relationship.tier = 2
        own_relationship.invested_depth = 10
        own_relationship.save()
        RelationshipLabelFactory(relationship=own_relationship, type=self.rel_type)

        thread = weave_thread(
            character_sheet=self.sheet,
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            target=own_relationship,
            resonance=self.resonance,
        )

        self.assertEqual(thread.owner, self.sheet)
        self.assertEqual(thread.target_relationship, own_relationship)

    def test_weaving_track_below_min_tier_raises(self) -> None:
        """A side at tier=1 with the default thread_min_tier=2 raises RelationshipTierTooLow."""
        own_relationship = CharacterRelationshipFactory(
            source=self.sheet, target=self.partner_sheet
        )
        own_relationship.tier = 1
        own_relationship.save()
        RelationshipLabelFactory(relationship=own_relationship, type=self.rel_type)

        pre_count = Thread.objects.filter(owner=self.sheet).count()
        with self.assertRaises(RelationshipTierTooLow):
            weave_thread(
                character_sheet=self.sheet,
                target_kind=TargetKind.RELATIONSHIP_TRACK,
                target=own_relationship,
                resonance=self.resonance,
            )
        self.assertEqual(Thread.objects.filter(owner=self.sheet).count(), pre_count)


class RelationshipCapstoneOwnershipTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.other_sheet = CharacterSheetFactory()
        cls.partner_sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory()
        cls.rel_type = RelationshipTypeFactory()
        unlock = ThreadWeavingUnlockFactory(
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            unlock_trait=None,
            unlock_type=cls.rel_type,
        )
        CharacterThreadWeavingUnlockFactory(character=cls.sheet, unlock=unlock)
        CharacterThreadWeavingUnlockFactory(character=cls.other_sheet, unlock=unlock)

        other_relationship = CharacterRelationshipFactory(
            source=cls.other_sheet, target=cls.partner_sheet
        )
        cls.other_capstone = RelationshipCapstoneFactory(
            relationship=other_relationship,
            tier_claimed=1,
            xp_spent=10,
            is_ritual_capstone=True,
        )

    def test_weaving_anothers_capstone_raises(self) -> None:
        pre_count = Thread.objects.filter(owner=self.sheet).count()
        with self.assertRaises(RelationshipBondNotOwned):
            weave_thread(
                character_sheet=self.sheet,
                target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
                target=self.other_capstone,
                resonance=self.resonance,
            )
        self.assertEqual(Thread.objects.filter(owner=self.sheet).count(), pre_count)

    def test_weaving_own_capstone_succeeds(self) -> None:
        own_relationship = CharacterRelationshipFactory(
            source=self.sheet, target=self.partner_sheet
        )
        own_capstone = RelationshipCapstoneFactory(
            relationship=own_relationship,
            tier_claimed=1,
            xp_spent=10,
            is_ritual_capstone=True,
        )

        thread = weave_thread(
            character_sheet=self.sheet,
            target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
            target=own_capstone,
            resonance=self.resonance,
        )

        self.assertEqual(thread.owner, self.sheet)
        self.assertEqual(thread.target_capstone, own_capstone)
