from django.db import IntegrityError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.entry_flourish import PendingEntryFlourishOffer, maybe_create_entry_flourish_offer
from world.magic.factories import (
    CharacterResonanceFactory,
    EntryFlourishRecordFactory,
    ResonanceFactory,
)
from world.scenes.factories import SceneFactory


class MaybeCreateOfferTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.claimed = CharacterResonanceFactory(character_sheet=cls.sheet)
        cls.scene = SceneFactory()

    def _character(self):
        return self.sheet.character

    def test_creates_offer_when_claimed_resonances_exist(self):
        offer = maybe_create_entry_flourish_offer(self._character(), self.scene)
        self.assertIsNotNone(offer)
        self.assertEqual(offer.scene_id, self.scene.pk)

    def test_idempotent_one_per_character(self):
        maybe_create_entry_flourish_offer(self._character(), self.scene)
        maybe_create_entry_flourish_offer(self._character(), self.scene)
        self.assertEqual(
            PendingEntryFlourishOffer.objects.filter(character_sheet=self.sheet).count(), 1
        )

    def test_no_offer_when_already_flourished_this_scene(self):
        EntryFlourishRecordFactory(character_sheet=self.sheet, scene=self.scene, granted_amount=10)
        self.assertIsNone(maybe_create_entry_flourish_offer(self._character(), self.scene))

    def test_no_offer_when_no_claimed_resonances(self):
        bare = CharacterSheetFactory()
        self.assertIsNone(maybe_create_entry_flourish_offer(bare.character, self.scene))


class PendingEntryFlourishOfferModelTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()

    def test_one_pending_offer_per_character(self):
        PendingEntryFlourishOffer.objects.create(character_sheet=self.sheet)
        with self.assertRaises(IntegrityError):
            PendingEntryFlourishOffer.objects.create(character_sheet=self.sheet)


class ResolveOfferTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.claimed = CharacterResonanceFactory(character_sheet=cls.sheet)
        cls.scene = SceneFactory()

    def test_resolve_fires_grant_and_deletes_offer(self):
        from world.magic.entry_flourish import resolve_entry_flourish_offer
        from world.magic.models import EntryFlourishRecord

        offer = PendingEntryFlourishOffer.objects.create(
            character_sheet=self.sheet, scene=self.scene
        )
        result = resolve_entry_flourish_offer(offer, resonance=self.claimed.resonance)
        self.assertEqual(result.resonance_id, self.claimed.resonance_id)
        self.assertFalse(PendingEntryFlourishOffer.objects.filter(pk=offer.pk).exists())
        self.assertTrue(
            EntryFlourishRecord.objects.filter(
                character_sheet=self.sheet, scene=self.scene
            ).exists()
        )

    def test_resolve_unclaimed_resonance_is_stale(self):
        from world.magic.entry_flourish import resolve_entry_flourish_offer
        from world.magic.exceptions import EntryFlourishOfferStaleError

        other = ResonanceFactory()
        offer = PendingEntryFlourishOffer.objects.create(
            character_sheet=self.sheet, scene=self.scene
        )
        with self.assertRaises(EntryFlourishOfferStaleError):
            resolve_entry_flourish_offer(offer, resonance=other)
        self.assertFalse(PendingEntryFlourishOffer.objects.filter(pk=offer.pk).exists())


class EntryFlourishRecordUniquenessTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.scene = SceneFactory()

    def test_unique_per_sheet_scene_when_scene_present(self):
        EntryFlourishRecordFactory(character_sheet=self.sheet, scene=self.scene, granted_amount=10)
        with self.assertRaises(IntegrityError):
            EntryFlourishRecordFactory(
                character_sheet=self.sheet, scene=self.scene, granted_amount=10
            )

    def test_scene_null_records_are_unconstrained(self):
        EntryFlourishRecordFactory(character_sheet=self.sheet, scene=None, granted_amount=10)
        EntryFlourishRecordFactory(character_sheet=self.sheet, scene=None, granted_amount=10)
        self.assertEqual(
            PendingEntryFlourishOffer.objects.count(), 0
        )  # sanity: offers untouched here
