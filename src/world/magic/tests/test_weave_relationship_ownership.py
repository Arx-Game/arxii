"""Tests for the RELATIONSHIP_TRACK/RELATIONSHIP_CAPSTONE ownership assertion in
``weave_thread`` (#2033).

A character may only weave a thread anchored on a relationship-track or
capstone row that belongs to THEIR OWN ``CharacterRelationship``
(``relationship.source``) — never someone else's relationship, even when
they hold a matching ``ThreadWeavingUnlock``. Before #2033, ``weave_thread``
checked the unlock only; a character who happened to hold ANY
RELATIONSHIP_TRACK unlock could weave a thread anchored on ANY character's
track-progress row.
"""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import TargetKind
from world.magic.exceptions import RelationshipBondNotOwned
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
    RelationshipTrackFactory,
    RelationshipTrackProgressFactory,
)


class RelationshipTrackOwnershipTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.other_sheet = CharacterSheetFactory()
        cls.partner_sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory()
        cls.track = RelationshipTrackFactory()
        unlock = ThreadWeavingUnlockFactory(
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            unlock_trait=None,
            unlock_track=cls.track,
        )
        # Both sheets hold the matching unlock — the unlock gate alone would let
        # either weave a RELATIONSHIP_TRACK thread; ownership must still gate it.
        CharacterThreadWeavingUnlockFactory(character=cls.sheet, unlock=unlock)
        CharacterThreadWeavingUnlockFactory(character=cls.other_sheet, unlock=unlock)

        other_relationship = CharacterRelationshipFactory(
            source=cls.other_sheet, target=cls.partner_sheet
        )
        cls.other_progress = RelationshipTrackProgressFactory(
            relationship=other_relationship, track=cls.track, developed_points=10
        )

    def test_weaving_anothers_track_row_raises(self) -> None:
        pre_count = Thread.objects.filter(owner=self.sheet).count()
        with self.assertRaises(RelationshipBondNotOwned):
            weave_thread(
                character_sheet=self.sheet,
                target_kind=TargetKind.RELATIONSHIP_TRACK,
                target=self.other_progress,
                resonance=self.resonance,
            )
        self.assertEqual(Thread.objects.filter(owner=self.sheet).count(), pre_count)

    def test_weaving_own_track_row_succeeds(self) -> None:
        own_relationship = CharacterRelationshipFactory(
            source=self.sheet, target=self.partner_sheet
        )
        own_progress = RelationshipTrackProgressFactory(
            relationship=own_relationship, track=self.track, developed_points=10
        )

        thread = weave_thread(
            character_sheet=self.sheet,
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            target=own_progress,
            resonance=self.resonance,
        )

        self.assertEqual(thread.owner, self.sheet)
        self.assertEqual(thread.target_relationship_track, own_progress)


class RelationshipCapstoneOwnershipTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.other_sheet = CharacterSheetFactory()
        cls.partner_sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory()
        cls.track = RelationshipTrackFactory()
        unlock = ThreadWeavingUnlockFactory(
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            unlock_trait=None,
            unlock_track=cls.track,
        )
        CharacterThreadWeavingUnlockFactory(character=cls.sheet, unlock=unlock)
        CharacterThreadWeavingUnlockFactory(character=cls.other_sheet, unlock=unlock)

        other_relationship = CharacterRelationshipFactory(
            source=cls.other_sheet, target=cls.partner_sheet
        )
        cls.other_capstone = RelationshipCapstoneFactory(
            relationship=other_relationship,
            author=cls.other_sheet,
            track=cls.track,
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
            author=self.sheet,
            track=self.track,
        )

        thread = weave_thread(
            character_sheet=self.sheet,
            target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
            target=own_capstone,
            resonance=self.resonance,
        )

        self.assertEqual(thread.owner, self.sheet)
        self.assertEqual(thread.target_capstone, own_capstone)
