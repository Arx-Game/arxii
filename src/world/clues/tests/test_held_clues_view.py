"""API tests for GET /api/clues/held/ (#1575).

The held-clue journal — private IC knowledge: a player only ever sees clues held by characters
they play, never another player's.
"""

from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.clues.constants import ClueTargetKind
from world.clues.factories import CharacterClueFactory, ClueFactory
from world.roster.factories import (
    PlayerDataFactory,
    RosterEntryFactory,
    RosterTenureFactory,
)

URL = "/api/clues/held/"


class HeldCluesViewTests(APITestCase):
    def setUp(self):
        self.user = AccountFactory()
        # One PlayerData per account (OneToOne); a player can hold many tenures on it.
        self.player_data = PlayerDataFactory(account=self.user)
        self.entry = RosterEntryFactory()
        RosterTenureFactory(roster_entry=self.entry, player_data=self.player_data)

    def _rows(self, response):
        return response.data["results"] if isinstance(response.data, dict) else response.data

    def test_requires_authentication(self):
        assert self.client.get(URL).status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    def test_lists_own_held_clues(self):
        clue = ClueFactory(name="Torn Journal Page", description="A page ripped from a diary.")
        CharacterClueFactory(roster_entry=self.entry, clue=clue)
        self.client.force_authenticate(user=self.user)
        response = self.client.get(URL)
        assert response.status_code == status.HTTP_200_OK
        rows = self._rows(response)
        assert len(rows) == 1
        assert rows[0]["name"] == "Torn Journal Page"
        assert rows[0]["description"] == "A page ripped from a diary."
        assert rows[0]["target_kind"] == ClueTargetKind.CODEX

    def test_does_not_leak_another_players_clues(self):
        other_entry = RosterEntryFactory()
        RosterTenureFactory(
            roster_entry=other_entry, player_data=PlayerDataFactory(account=AccountFactory())
        )
        CharacterClueFactory(roster_entry=other_entry)
        self.client.force_authenticate(user=self.user)
        response = self.client.get(URL)
        assert response.status_code == status.HTTP_200_OK
        assert self._rows(response) == []

    def test_filters_by_character_sheet(self):
        # The account plays two characters; the filter narrows to one.
        clue_a = ClueFactory(name="Clue A")
        CharacterClueFactory(roster_entry=self.entry, clue=clue_a)
        second_entry = RosterEntryFactory()
        RosterTenureFactory(roster_entry=second_entry, player_data=self.player_data)
        CharacterClueFactory(roster_entry=second_entry, clue=ClueFactory(name="Clue B"))

        self.client.force_authenticate(user=self.user)
        response = self.client.get(URL, {"character_sheet": self.entry.character_sheet_id})
        assert response.status_code == status.HTTP_200_OK
        rows = self._rows(response)
        assert [r["name"] for r in rows] == ["Clue A"]

    def test_empty_when_no_clues(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(URL)
        assert response.status_code == status.HTTP_200_OK
        assert self._rows(response) == []
