from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import GainSource
from world.magic.factories import (
    CharacterResonanceFactory,
    EntryFlourishRecordFactory,
    ResonanceFactory,
)
from world.magic.models import CharacterResonance, EntryFlourishRecord, ResonanceGrant
from world.magic.services.gain import create_entry_flourish


class EntryFlourishRecordModelTest(TestCase):
    def test_create_entry_flourish_record(self):
        record = EntryFlourishRecordFactory(granted_amount=10)
        self.assertIsInstance(record, EntryFlourishRecord)
        self.assertEqual(record.granted_amount, 10)
        self.assertIsNotNone(record.resonance_id)
        self.assertIsNotNone(record.character_sheet_id)
        self.assertIsNotNone(record.created_at)

    def test_str(self):
        record = EntryFlourishRecordFactory()
        self.assertIn("EntryFlourishRecord", str(record))


class CreateEntryFlourishServiceTest(TestCase):
    def setUp(self):
        self.sheet = CharacterSheetFactory()
        self.resonance = ResonanceFactory()
        CharacterResonanceFactory(
            character_sheet=self.sheet,
            resonance=self.resonance,
            balance=0,
            lifetime_earned=0,
        )

    def test_creates_entry_flourish_record(self):
        record = create_entry_flourish(self.sheet, self.resonance, scene=None)
        self.assertIsInstance(record, EntryFlourishRecord)
        self.assertEqual(record.character_sheet, self.sheet)
        self.assertEqual(record.resonance, self.resonance)
        self.assertIsNone(record.scene)

    def test_grants_resonance_from_config(self):
        create_entry_flourish(self.sheet, self.resonance, scene=None)
        cr = CharacterResonance.objects.get(character_sheet=self.sheet, resonance=self.resonance)
        self.assertEqual(cr.balance, 10)  # config default

    def test_writes_grant_ledger_row(self):
        create_entry_flourish(self.sheet, self.resonance, scene=None)
        grant = ResonanceGrant.objects.get(
            character_sheet=self.sheet, source=GainSource.ENTRY_FLOURISH
        )
        self.assertEqual(grant.amount, 10)
        self.assertIsNotNone(grant.source_entry_flourish_id)

    def test_custom_amount_overrides_config(self):
        create_entry_flourish(self.sheet, self.resonance, scene=None, amount=25)
        cr = CharacterResonance.objects.get(character_sheet=self.sheet, resonance=self.resonance)
        self.assertEqual(cr.balance, 25)

    def test_character_must_have_claimed_resonance(self):
        from world.magic.exceptions import EndorsementValidationError

        other_resonance = ResonanceFactory()
        with self.assertRaises(EndorsementValidationError):
            create_entry_flourish(self.sheet, other_resonance, scene=None)

    def test_skips_grant_gracefully_on_duplicate_scene(self):
        from world.scenes.factories import SceneFactory

        scene = SceneFactory()
        first = create_entry_flourish(self.sheet, self.resonance, scene=scene)
        grants_before = ResonanceGrant.objects.filter(
            character_sheet=self.sheet, source=GainSource.ENTRY_FLOURISH
        ).count()
        second = create_entry_flourish(self.sheet, self.resonance, scene=scene)
        self.assertEqual(second.pk, first.pk)  # returns existing, no new record
        grants_after = ResonanceGrant.objects.filter(
            character_sheet=self.sheet, source=GainSource.ENTRY_FLOURISH
        ).count()
        self.assertEqual(grants_after, grants_before)  # no second grant
