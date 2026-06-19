from django.db import IntegrityError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.entry_flourish import PendingEntryFlourishOffer
from world.magic.factories import EntryFlourishRecordFactory
from world.scenes.factories import SceneFactory


class PendingEntryFlourishOfferModelTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()

    def test_one_pending_offer_per_character(self):
        PendingEntryFlourishOffer.objects.create(character_sheet=self.sheet)
        with self.assertRaises(IntegrityError):
            PendingEntryFlourishOffer.objects.create(character_sheet=self.sheet)


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
