"""
Tests for active_player_character_sheets selector.
"""

from __future__ import annotations

from django.test import TestCase
from django.utils import timezone

from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.roster.selectors import active_player_character_sheets


class ActivePlayerCharacterSheetsTest(TestCase):
    """Tests for active_player_character_sheets selector."""

    @classmethod
    def setUpTestData(cls) -> None:
        # Entry with a current (unended) tenure
        cls.active_sheet = CharacterSheetFactory()
        cls.active_entry = RosterEntryFactory(character_sheet=cls.active_sheet)
        RosterTenureFactory(roster_entry=cls.active_entry)  # end_date=None by default

        # Entry with an ended tenure only
        cls.inactive_sheet = CharacterSheetFactory()
        cls.inactive_entry = RosterEntryFactory(character_sheet=cls.inactive_sheet)
        RosterTenureFactory(roster_entry=cls.inactive_entry, end_date=timezone.now())

        # Entry with no tenure at all
        cls.no_tenure_sheet = CharacterSheetFactory()
        RosterEntryFactory(character_sheet=cls.no_tenure_sheet)

    def test_returns_only_active_sheet(self) -> None:
        """Only the sheet whose entry has a current tenure is returned."""
        result = active_player_character_sheets()

        pks = [sheet.pk for sheet in result]
        assert self.active_sheet.pk in pks
        assert self.inactive_sheet.pk not in pks
        assert self.no_tenure_sheet.pk not in pks

    def test_no_duplicates_with_multiple_tenures(self) -> None:
        """A sheet with both an ended and a current tenure appears only once."""
        multi_sheet = CharacterSheetFactory()
        multi_entry = RosterEntryFactory(character_sheet=multi_sheet)
        # Ended tenure
        RosterTenureFactory(roster_entry=multi_entry, end_date=timezone.now())
        # Current tenure
        RosterTenureFactory(roster_entry=multi_entry)

        result = active_player_character_sheets()

        matching = [s for s in result if s.pk == multi_sheet.pk]
        assert len(matching) == 1

    def test_returns_list(self) -> None:
        """Return type is a list."""
        result = active_player_character_sheets()
        assert isinstance(result, list)

    def test_sheet_with_no_tenure_not_returned(self) -> None:
        """A sheet whose entry has no tenures at all is not returned (LEFT JOIN guard)."""
        result = active_player_character_sheets()
        pks = [sheet.pk for sheet in result]
        assert self.no_tenure_sheet.pk not in pks
