"""View tests for the #3412 character-selection endpoint
(`POST /api/roster/entries/select/`) — state 2.5 substrate.

Mirrors the persona set-active endpoint's shape/validation posture: uniform
rejection for a foreign/unknown entry, `entry_id: null` always clears, and
zero lifecycle/session/puppeting side effects on success.
"""

from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import (
    PlayerDataFactory,
    RosterEntryFactory,
    RosterTenureFactory,
)
from world.roster.models import RosterTenure


def _entry_for(player_data):
    character = CharacterFactory()
    sheet = CharacterSheetFactory(character=character)
    entry = RosterEntryFactory(character_sheet=sheet)
    RosterTenureFactory(player_data=player_data, roster_entry=entry)
    return entry


class SelectEntryViewTests(TestCase):
    url = "/api/roster/entries/select/"

    def setUp(self):
        self.client = APIClient()
        self.player = PlayerDataFactory()
        self.entry = _entry_for(self.player)
        self.client.force_authenticate(user=self.player.account)

    def test_select_own_entry_ok(self):
        response = self.client.post(self.url, {"entry_id": self.entry.pk}, format="json")

        assert response.status_code == 200
        assert response.data["selected_entry_id"] == self.entry.pk
        assert response.data["selected_entry"]["id"] == self.entry.pk
        assert response.data["selected_entry"]["name"] == self.entry.character_sheet.character.key
        self.player.refresh_from_db()
        assert self.player.selected_entry_id == self.entry.pk

    def test_select_foreign_entry_rejected(self):
        other_player = PlayerDataFactory()
        foreign_entry = _entry_for(other_player)

        response = self.client.post(self.url, {"entry_id": foreign_entry.pk}, format="json")

        assert response.status_code == 400
        self.player.refresh_from_db()
        assert self.player.selected_entry_id is None

    def test_select_unknown_entry_id_rejected(self):
        response = self.client.post(self.url, {"entry_id": 999999}, format="json")

        assert response.status_code == 400

    def test_select_clear_ok(self):
        self.client.post(self.url, {"entry_id": self.entry.pk}, format="json")

        response = self.client.post(self.url, {"entry_id": None}, format="json")

        assert response.status_code == 200
        assert response.data["selected_entry_id"] is None
        assert response.data["selected_entry"] is None
        self.player.refresh_from_db()
        assert self.player.selected_entry_id is None

    def test_select_clear_with_no_prior_selection_ok(self):
        response = self.client.post(self.url, {"entry_id": None}, format="json")

        assert response.status_code == 200
        assert response.data["selected_entry_id"] is None

    def test_select_requires_authentication(self):
        anon_client = APIClient()

        response = anon_client.post(self.url, {"entry_id": self.entry.pk}, format="json")

        assert response.status_code in (401, 403)

    def test_select_missing_entry_id_key_rejected(self):
        response = self.client.post(self.url, {}, format="json")

        assert response.status_code == 400

    def test_select_triggers_no_lifecycle_or_session_side_effects(self):
        """Selecting a character requires and creates no presence state."""
        tenure_count_before = RosterTenure.objects.count()
        assert self.entry.last_puppeted is None
        assert not self.player.account.sessions.all()

        response = self.client.post(self.url, {"entry_id": self.entry.pk}, format="json")

        assert response.status_code == 200
        assert RosterTenure.objects.count() == tenure_count_before
        self.entry.refresh_from_db()
        assert self.entry.last_puppeted is None
        assert not self.player.account.sessions.all()
