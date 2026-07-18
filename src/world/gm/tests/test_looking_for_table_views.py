"""Tests for the looking-for-table API endpoints (#2431)."""

from __future__ import annotations

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.factories import GMProfileFactory
from world.gm.services import set_looking_for_table
from world.roster.factories import (
    PlayerDataFactory,
    RosterEntryFactory,
    RosterTenureFactory,
)


def _make_roster_entry_with_player(player_data):
    """Build a roster entry with a tenure linked to the given player_data."""
    char = CharacterFactory()
    sheet = CharacterSheetFactory(character=char)
    roster_entry = RosterEntryFactory(character_sheet=sheet)
    RosterTenureFactory(player_data=player_data, roster_entry=roster_entry)
    return roster_entry


class LookingForTableToggleViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.account = AccountFactory()
        self.player_data = PlayerDataFactory(account=self.account)
        self.client.force_authenticate(user=self.account)

    def test_set_flag(self):
        """POST looking=true sets the flag."""
        url = reverse("roster:looking-for-table-toggle")
        response = self.client.post(url, {"looking": True}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["looking_for_table"])
        self.player_data.refresh_from_db()
        self.assertTrue(self.player_data.looking_for_table)

    def test_clear_flag(self):
        """POST looking=false clears the flag."""
        set_looking_for_table(self.player_data, looking=True)
        url = reverse("roster:looking-for-table-toggle")
        response = self.client.post(url, {"looking": False}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["looking_for_table"])
        self.player_data.refresh_from_db()
        self.assertFalse(self.player_data.looking_for_table)

    def test_requires_looking_field(self):
        """POST without looking field returns 400."""
        url = reverse("roster:looking-for-table-toggle")
        response = self.client.post(url, {}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_requires_auth(self):
        """POST without auth returns 401/403."""
        self.client.force_authenticate(user=None)
        url = reverse("roster:looking-for-table-toggle")
        response = self.client.post(url, {"looking": True}, format="json")
        self.assertIn(response.status_code, (401, 403))


class LookingForTableBrowseViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.gm_account = AccountFactory()
        GMProfileFactory(account=self.gm_account)
        self.client.force_authenticate(user=self.gm_account)

    def test_gm_sees_looking_for_table_players(self):
        """GET returns players with the looking-for-table flag set."""
        player_data = PlayerDataFactory()
        set_looking_for_table(player_data, looking=True)
        _make_roster_entry_with_player(player_data)

        # Another player NOT looking for a table
        other_pd = PlayerDataFactory()
        _make_roster_entry_with_player(other_pd)

        url = reverse("gm:gm-looking-for-table")
        response = self.client.get(url, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)

    def test_non_gm_forbidden(self):
        """GET by a non-GM account returns 403."""
        regular_account = AccountFactory()
        PlayerDataFactory(account=regular_account)
        self.client.force_authenticate(user=regular_account)
        url = reverse("gm:gm-looking-for-table")
        response = self.client.get(url, format="json")
        self.assertEqual(response.status_code, 403)
