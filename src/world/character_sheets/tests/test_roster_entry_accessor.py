"""CharacterSheet.roster_entry_or_none — the safe reverse-OneToOne accessor (audit).

Replaces the ``getattr(sheet, "roster_entry", None)`` idiom: the reverse OneToOne
raises RelatedObjectDoesNotExist (an AttributeError subclass), so getattr-with-default
silently swallowed real attribute bugs along with the expected miss.
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import RosterEntryFactory


class RosterEntryOrNoneTests(TestCase):
    def test_sheet_with_entry_returns_it(self):
        entry = RosterEntryFactory()
        assert entry.character_sheet.roster_entry_or_none == entry

    def test_sheet_without_entry_returns_none(self):
        sheet = CharacterSheetFactory()
        assert sheet.roster_entry_or_none is None
