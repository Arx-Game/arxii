"""Tests for a player giving up a roster character (#3996): ``release_tenure``."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.types import ActivityState
from world.roster.factories import (
    PlayerDataFactory,
    RosterEntryFactory,
    RosterFactory,
    RosterTenureFactory,
)
from world.roster.models.choices import CreationProvenance, RosterType
from world.roster.seeds import ensure_rosters
from world.roster.services.activity import (
    FreezeError,
    ReleaseError,
    freeze_character,
    is_original_character,
    release_tenure,
)


def _held(provenance: str):
    """A current tenure on an Active-shelf entry with the given provenance."""
    entry = RosterEntryFactory(
        character_sheet=CharacterSheetFactory(),
        roster=RosterFactory(roster_type=RosterType.ACTIVE),
        creation_provenance=provenance,
    )
    tenure = RosterTenureFactory(roster_entry=entry)
    return entry, tenure


class ReleaseTenureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_rosters()

    def test_roster_character_returns_to_available_and_tenure_ends(self):
        entry, tenure = _held(CreationProvenance.STAFF)
        release_tenure(entry.character_sheet, player_data=tenure.player_data)
        tenure.refresh_from_db()
        entry.refresh_from_db()
        assert tenure.end_date is not None
        assert entry.roster.roster_type == RosterType.AVAILABLE
        assert entry.current_tenure is None

    def test_original_character_is_refused(self):
        entry, tenure = _held(CreationProvenance.PLAYER)
        with self.assertRaises(ReleaseError) as ctx:
            release_tenure(entry.character_sheet, player_data=tenure.player_data)
        assert "frozen, not given up" in ctx.exception.user_message

    def test_another_players_character_is_refused(self):
        entry, _tenure = _held(CreationProvenance.GM_TABLE)
        stranger = PlayerDataFactory()
        with self.assertRaises(ReleaseError):
            release_tenure(entry.character_sheet, player_data=stranger)
        entry.refresh_from_db()
        assert entry.roster.roster_type == RosterType.ACTIVE

    def test_puppeted_character_is_refused(self):
        import evennia

        entry, tenure = _held(CreationProvenance.STAFF)
        character = entry.character_sheet.character
        # ObjectSessionHandler only trusts session ids the server handler knows.
        evennia.SESSION_HANDLER[42] = object()
        self.addCleanup(evennia.SESSION_HANDLER.pop, 42, None)
        character.db_sessid = "42"
        character.save(update_fields=["db_sessid"])
        with self.assertRaises(ReleaseError) as ctx:
            release_tenure(entry.character_sheet, player_data=tenure.player_data)
        assert "Leave the world" in ctx.exception.user_message


class ProvenanceIsTheOcRuleTests(TestCase):
    def test_player_provenance_is_an_original_character(self):
        entry, _ = _held(CreationProvenance.PLAYER)
        assert is_original_character(entry.character_sheet)
        freeze_character(entry.character_sheet)
        entry.character_sheet.refresh_from_db()
        assert entry.character_sheet.activity_state == ActivityState.FROZEN

    def test_staff_provenance_cannot_be_frozen(self):
        entry, _ = _held(CreationProvenance.STAFF)
        assert not is_original_character(entry.character_sheet)
        with self.assertRaises(FreezeError):
            freeze_character(entry.character_sheet)

    def test_sheet_without_entry_is_not_an_original_character(self):
        assert not is_original_character(CharacterSheetFactory())
