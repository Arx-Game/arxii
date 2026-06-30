"""Gossip web API (#1572) — the GossipListView / GossipActionView plumbing.

The gossip *mechanic* is exercised (on Postgres) in test_gossip.py; here the services are mocked so
these stay on SQLite and focus on the view layer: for_account scoping, serialization, dispatch, and
GossipError → user_message responses.
"""

from unittest.mock import patch

from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, RoomProfileFactory
from evennia_extensions.models import PlayerData
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.secrets.constants import SecretLevel
from world.secrets.factories import SecretFactory
from world.secrets.gossip import GossipError, GossipResult

LIST_URL = "/api/secrets/gossip/"
ACTION_URL = "/api/secrets/gossip/action/"


class GossipApiTests(APITestCase):
    def setUp(self) -> None:
        self.account = AccountFactory()
        player_data, _ = PlayerData.objects.get_or_create(account=self.account)
        self.entry = RosterEntryFactory()
        RosterTenureFactory(player_data=player_data, roster_entry=self.entry)
        self.character = self.entry.character_sheet.character
        # Give the character a room so the action endpoints don't 400 as roomless.
        self.character.db_location = RoomProfileFactory(is_social_hub=True).objectdb
        self.character.save()
        self.secret = SecretFactory(level=SecretLevel.UNCOMMON_KNOWLEDGE, content="A scandal.")
        self.client.force_authenticate(user=self.account)

    @patch("world.secrets.gossip.region_heat_for", return_value=5)
    @patch("world.secrets.gossip.spreadable_secrets")
    def test_list_returns_spreadable_with_heat(self, mock_spread, _mock_heat) -> None:  # noqa: PT019
        mock_spread.return_value = [self.secret]
        rows = self.client.get(LIST_URL, {"viewer": self.entry.pk}).data
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], self.secret.pk)
        self.assertEqual(rows[0]["content"], "A scandal.")
        self.assertEqual(rows[0]["heat"], 5)

    def test_list_unowned_viewer_is_empty(self) -> None:
        other = RosterEntryFactory()  # not owned by self.account
        self.assertEqual(self.client.get(LIST_URL, {"viewer": other.pk}).data, [])

    @patch("world.secrets.gossip.seek_gossip")
    def test_seek_dispatches_and_returns_result(self, mock_seek) -> None:
        mock_seek.return_value = GossipResult(
            success=True, heat=0, surfaced_secret_id=self.secret.pk
        )
        res = self.client.post(
            ACTION_URL, {"action": "seek", "viewer": self.entry.pk}, format="json"
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["success"])
        # A successful seek surfaces the overheard rumor's text.
        self.assertEqual(res.data["content"], "A scandal.")

    @patch("world.secrets.gossip.plant_gossip")
    def test_plant_dispatches(self, mock_plant) -> None:
        mock_plant.return_value = GossipResult(success=True, heat=2)
        res = self.client.post(
            ACTION_URL,
            {"action": "plant", "viewer": self.entry.pk, "secret": self.secret.pk},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["heat"], 2)
        mock_plant.assert_called_once()

    @patch("world.secrets.gossip.plant_gossip")
    def test_gossip_error_surfaces_user_message(self, mock_plant) -> None:
        mock_plant.side_effect = GossipError("x", user_message="You don't have the ear for it.")
        res = self.client.post(
            ACTION_URL,
            {"action": "plant", "viewer": self.entry.pk, "secret": self.secret.pk},
            format="json",
        )
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.data["detail"], "You don't have the ear for it.")

    def test_plant_requires_a_secret(self) -> None:
        res = self.client.post(
            ACTION_URL, {"action": "plant", "viewer": self.entry.pk}, format="json"
        )
        self.assertEqual(res.status_code, 400)

    def test_unowned_viewer_on_action_is_forbidden(self) -> None:
        other = RosterEntryFactory()
        res = self.client.post(ACTION_URL, {"action": "seek", "viewer": other.pk}, format="json")
        self.assertEqual(res.status_code, 403)
