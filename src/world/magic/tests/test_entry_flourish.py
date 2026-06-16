from django.test import TestCase

from world.magic.factories import EntryFlourishRecordFactory
from world.magic.models import EntryFlourishRecord


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
