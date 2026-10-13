"""Presence is a server fact (#4321): ``mine`` says whether a character is in the
world and where, and ``disconnect`` takes it off the grid from any tab."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase
from evennia.objects.models import ObjectDB
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import (
    PlayerDataFactory,
    RosterEntryFactory,
    RosterFactory,
    RosterTenureFactory,
)
from world.roster.models.choices import RosterType
from world.roster.seeds import ensure_rosters
from world.roster.services.presence import QUIT_REASON, disconnect_everywhere, session_count


def _puppet(test, entry, *sessids: int):
    """Fake ``sessids`` puppeting the entry's character. ObjectSessionHandler only
    trusts session ids the server handler knows (test_release_tenure does the same),
    and it caches them on the instance, so the sessions are added through the
    handler on the identity-mapped row the view will serialize, not on the deep copy
    setUpTestData hands each test."""
    import evennia

    character = ObjectDB.objects.get(pk=entry.character_sheet.character_id)
    for sessid in sessids:
        evennia.SESSION_HANDLER[sessid] = object()
        test.addCleanup(evennia.SESSION_HANDLER.pop, sessid, None)
        character.sessions.add(sessid)
    test.addCleanup(character.sessions.clear)
    return character


def _held(player_data):
    entry = RosterEntryFactory(
        character_sheet=CharacterSheetFactory(),
        roster=RosterFactory(roster_type=RosterType.ACTIVE),
    )
    RosterTenureFactory(roster_entry=entry, player_data=player_data)
    return entry


class MinePresenceTests(TestCase):
    url = "/api/roster/entries/mine/"

    @classmethod
    def setUpTestData(cls):
        ensure_rosters()
        cls.account = AccountFactory()
        cls.player_data = PlayerDataFactory(account=cls.account)
        cls.entry = _held(cls.player_data)
        cls.room = ObjectDBFactory(
            db_key="The Wanderer's Rest", db_typeclass_path="typeclasses.rooms.Room"
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)

    def _puppet(self, *sessids: int):
        character = _puppet(self, self.entry, *sessids)
        character.db_location = self.room
        character.save(update_fields=["db_location"])
        return character

    def test_out_of_the_world(self):
        row = self.client.get(self.url).data[0]
        assert row["session_count"] == 0
        assert row["room_name"] is None

    def test_a_location_without_a_session_is_not_presence(self):
        character = self.entry.character_sheet.character
        character.db_location = self.room
        character.save(update_fields=["db_location"])
        row = self.client.get(self.url).data[0]
        assert row["session_count"] == 0
        assert row["room_name"] is None

    def test_in_the_world_from_two_tabs(self):
        self._puppet(42, 43)
        row = self.client.get(self.url).data[0]
        assert row["session_count"] == 2
        assert row["room_name"] == "The Wanderer's Rest"


class DisconnectEverywhereTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_rosters()
        cls.account = AccountFactory()
        cls.player_data = PlayerDataFactory(account=cls.account)
        cls.entry = _held(cls.player_data)
        cls.stranger = AccountFactory()
        PlayerDataFactory(account=cls.stranger)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)

    def _puppet(self, *sessids: int):
        return _puppet(self, self.entry, *sessids)

    def test_closes_every_session_with_the_quit_reason(self):
        character = self._puppet(42, 43)
        with patch("evennia.SESSION_HANDLER.disconnect") as disconnect:
            closed = disconnect_everywhere(character)
        assert closed == 2
        assert disconnect.call_count == 2
        for call in disconnect.call_args_list:
            assert call.kwargs["reason"] == QUIT_REASON
        assert QUIT_REASON == "quit"

    def test_the_endpoint_reports_what_it_closed(self):
        self._puppet(42)
        with patch("evennia.SESSION_HANDLER.disconnect"):
            response = self.client.post(f"/api/roster/entries/{self.entry.pk}/disconnect/")
        assert response.status_code == 200, response.content
        assert response.data == {"closed": 1}

    def test_nothing_to_close_is_not_an_error(self):
        response = self.client.post(f"/api/roster/entries/{self.entry.pk}/disconnect/")
        assert response.status_code == 200, response.content
        assert response.data == {"closed": 0}
        assert session_count(self.entry.character_sheet.character) == 0

    def test_a_strangers_character_is_refused(self):
        self._puppet(42)
        self.client.force_authenticate(user=self.stranger)
        with patch("evennia.SESSION_HANDLER.disconnect") as disconnect:
            response = self.client.post(f"/api/roster/entries/{self.entry.pk}/disconnect/")
        assert response.status_code == 400
        assert "one of your characters" in response.content.decode()
        disconnect.assert_not_called()
