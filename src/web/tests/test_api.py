from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB
from evennia.objects.models import ObjectDB

from world.roster.models import Roster, RosterEntry


class WebAPITests(TestCase):
    def setUp(self):
        self.account = AccountDB.objects.create_user(
            username="tester", email="tester@test.com", password="pass"
        )

    @patch("web.api.views.SESSION_HANDLER")
    def test_homepage_api_returns_stats(self, mock_session_handler):
        mock_session_handler.account_count.return_value = 0
        url = reverse("api-homepage")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["page_title"], "Arx II")
        self.assertEqual(data["num_accounts_registered"], 1)
        self.assertEqual(data["num_accounts_connected"], 0)
        self.assertEqual(data["num_accounts_registered_recent"], 1)
        self.assertEqual(data["num_accounts_connected_recent"], 0)
        self.assertIsInstance(data["accounts_connected_recent"], list)

    @patch("web.api.views.SESSION_HANDLER")
    def test_status_api_returns_counts(self, mock_session_handler):
        mock_session_handler.account_count.return_value = 2
        url = reverse("api-status")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["online"], 2)
        self.assertEqual(data["total"], AccountDB.objects.count())

    def test_login_api_returns_user_on_post(self):
        url = reverse("api-login")
        response = self.client.post(url, {"username": "tester", "password": "pass"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["username"], "tester")

    def test_roster_detail_api_returns_data(self):
        character = ObjectDB.objects.create(
            db_key="Hero", db_typeclass_path="typeclasses.characters.Character"
        )
        roster = Roster.objects.create(name="Active")
        entry = RosterEntry.objects.create(character=character, roster=roster)
        url = reverse("roster-detail", args=[entry.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], entry.id)
        self.assertEqual(data["character"]["name"], "Hero")

    def test_my_characters_api_returns_empty_list(self):
        self.client.force_login(self.account)
        url = reverse("roster-mine")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data, [])

        self.client.logout()

    def test_roster_application_api_accepts_message(self):
        character = ObjectDB.objects.create(
            db_key="Hero", db_typeclass_path="typeclasses.characters.Character"
        )
        roster = Roster.objects.create(name="Active")
        entry = RosterEntry.objects.create(character=character, roster=roster)
        self.client.force_login(self.account)
        url = reverse("roster-apply", args=[entry.id])
        response = self.client.post(url, {"message": "Let me play"})
        self.assertEqual(response.status_code, 204)
