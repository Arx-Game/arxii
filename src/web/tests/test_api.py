from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from evennia.accounts.models import AccountDB
from evennia.objects.models import ObjectDB

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from flows.factories import SceneDataManagerFactory
from world.roster.factories import (
    PlayerDataFactory,
    RosterEntryFactory,
    RosterTenureFactory,
    TenureDisplaySettingsFactory,
)
from world.roster.models import Roster, RosterEntry


class WebAPITests(TestCase):
    def setUp(self):
        self.account = AccountDB.objects.create_user(
            username="tester", email="tester@test.com", password="pass"
        )

    @patch("web.api.views.general_views.SESSION_HANDLER")
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

    @patch("web.api.views.general_views.SESSION_HANDLER")
    def test_status_api_returns_counts(self, mock_session_handler):
        mock_session_handler.account_count.return_value = 2
        character = ObjectDB.objects.create(
            db_key="Char",
            db_typeclass_path="typeclasses.characters.Character",
            db_account=self.account,
        )
        entry = RosterEntry.objects.create(
            character=character, roster=Roster.objects.create(name="Active")
        )
        entry.last_puppeted = timezone.now()
        entry.save()
        ObjectDB.objects.create(
            db_key="Room", db_typeclass_path="typeclasses.rooms.Room"
        )
        url = reverse("api-status")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["online"], 2)
        self.assertEqual(data["accounts"], AccountDB.objects.count())
        self.assertEqual(data["characters"], 1)
        self.assertEqual(data["rooms"], 1)
        self.assertEqual(len(data["recentPlayers"]), 1)
        self.assertEqual(data["recentPlayers"][0]["name"], "Char")
        self.assertIsInstance(data["news"], list)

    def test_login_api_returns_user_on_post(self):
        url = reverse("api-login")
        response = self.client.post(url, {"username": "tester", "password": "pass"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["username"], "tester")

    def test_register_api_creates_user(self):
        url = reverse("api-register")
        response = self.client.post(
            url,
            {
                "username": "newuser",
                "password": "secret",
                "email": "new@test.com",
            },
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(AccountDB.objects.filter(username="newuser").exists())

    def test_register_api_rejects_duplicates(self):
        url = reverse("api-register")
        response = self.client.post(
            url,
            {
                "username": "tester",
                "password": "secret",
                "email": "tester@test.com",
            },
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("username", data)
        self.assertIn("email", data)

    def test_register_availability_api_returns_flags(self):
        url = reverse("api-register-availability")
        response = self.client.get(
            url, {"username": "tester", "email": "tester@test.com"}
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["username"])
        self.assertFalse(data["email"])

        response = self.client.get(
            url, {"username": "newuser", "email": "new@test.com"}
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["username"])
        self.assertTrue(data["email"])

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

    @patch("web.api.views.search_views.AccountDB.objects.get_connected_accounts")
    def test_online_character_search_returns_results(self, mock_connected):
        mock_connected.return_value = [self.account]
        player_data = PlayerDataFactory(account=self.account)
        character = CharacterFactory(db_key="Bob")
        entry = RosterEntryFactory(character=character)
        tenure = RosterTenureFactory(roster_entry=entry, player_data=player_data)
        TenureDisplaySettingsFactory(tenure=tenure)
        self.client.force_login(self.account)
        url = reverse("api-online-characters")
        response = self.client.get(url, {"search": "Bob"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [{"value": "Bob", "label": "Bob"}])

    @patch("web.api.views.search_views.AccountDB.get_puppeted_characters")
    def test_room_character_search_respects_display_name(self, mock_puppets):
        room = ObjectDBFactory(
            db_key="hall", db_typeclass_path="typeclasses.rooms.Room"
        )
        caller = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
            db_account=self.account,
        )
        target = ObjectDBFactory(
            db_key="Bob",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        context = SceneDataManagerFactory()
        context.initialize_state_for_object(room)
        context.initialize_state_for_object(caller)
        target_state = context.initialize_state_for_object(target)
        target_state.fake_name = "Masked"
        mock_puppets.return_value = [caller]
        self.client.force_login(self.account)
        url = reverse("api-room-characters")
        response = self.client.get(url, {"search": "mask"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [{"value": "Masked", "label": "Masked"}])
