"""Tests for the JournalEntry.related_threads M2M (Spec A §2.2)."""

from django.test import TestCase

from world.journals.factories import JournalEntryFactory
from world.magic.factories import ThreadFactory


class RelatedThreadsM2MTests(TestCase):
    def test_attach_thread_to_journal_entry(self) -> None:
        entry = JournalEntryFactory()
        thread = ThreadFactory()
        entry.related_threads.add(thread)
        self.assertIn(thread, entry.related_threads.all())

    def test_thread_lists_related_journal_entries(self) -> None:
        entry = JournalEntryFactory()
        thread = ThreadFactory()
        entry.related_threads.add(thread)
        # Reverse relation
        self.assertIn(entry, thread.related_journal_entries.all())
