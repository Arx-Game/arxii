from unittest.mock import patch

from allauth.account.models import EmailConfirmation
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from evennia.accounts.models import AccountDB
from evennia.objects.models import ObjectDB

from evennia_extensions.factories import (
    CharacterFactory,
    EmailAddressFactory,
    EmailConfirmationFactory,
    ObjectDBFactory,
)
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
            username="tester",
            email="tester@test.com",
            password="pass",
        )

    @patch("web.api.views.general_views.SESSION_HANDLER")
    def test_homepage_api_returns_stats(self, mock_session_handler):
        mock_session_handler.account_count.return_value = 0
        url = reverse("api-homepage")
        response = self.client.get(url)
        assert response.status_code == 200
        data = response.json()
        assert data["page_title"] == "Arx II"
        assert data["num_accounts_registered"] == 1
        assert data["num_accounts_connected"] == 0
        assert data["num_accounts_registered_recent"] == 1
        assert data["num_accounts_connected_recent"] == 0
        assert isinstance(data["accounts_connected_recent"], list)

    @patch("web.api.views.general_views.SESSION_HANDLER")
    def test_status_api_returns_counts(self, mock_session_handler):
        mock_session_handler.account_count.return_value = 2
        character = ObjectDB.objects.create(
            db_key="Char",
            db_typeclass_path="typeclasses.characters.Character",
            db_account=self.account,
        )
        entry = RosterEntry.objects.create(
            character=character,
            roster=Roster.objects.create(name="Active"),
        )
        entry.last_puppeted = timezone.now()
        entry.save()
        ObjectDB.objects.create(
            db_key="Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        url = reverse("api-status")
        response = self.client.get(url)
        assert response.status_code == 200
        data = response.json()
        assert data["online"] == 2
        assert data["accounts"] == AccountDB.objects.count()
        assert data["characters"] == 1
        assert data["rooms"] == 1
        assert len(data["recentPlayers"]) == 1
        assert data["recentPlayers"][0]["name"] == "Char"
        assert isinstance(data["news"], list)

    def test_login_api_returns_user_on_post(self):
        url = reverse("api-login")
        response = self.client.post(url, {"username": "tester", "password": "pass"})
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "tester"

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
        assert response.status_code == 201
        assert AccountDB.objects.filter(username="newuser").exists()

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
        assert response.status_code == 400
        data = response.json()
        assert "username" in data
        assert "email" in data

    def test_register_availability_api_returns_flags(self):
        url = reverse("api-register-availability")
        response = self.client.get(
            url,
            {"username": "tester", "email": "tester@test.com"},
        )
        assert response.status_code == 200
        data = response.json()
        assert not data["username"]
        assert not data["email"]

        response = self.client.get(
            url,
            {"username": "newuser", "email": "new@test.com"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["username"]
        assert data["email"]

    def test_roster_detail_api_returns_data(self):
        character = ObjectDB.objects.create(
            db_key="Hero",
            db_typeclass_path="typeclasses.characters.Character",
        )
        roster = Roster.objects.create(name="Active")
        entry = RosterEntry.objects.create(character=character, roster=roster)
        url = reverse("roster-detail", args=[entry.id])
        response = self.client.get(url)
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == entry.id
        assert data["character"]["name"] == "Hero"

    def test_my_characters_api_returns_empty_list(self):
        self.client.force_login(self.account)
        url = reverse("roster-mine")
        response = self.client.get(url)
        assert response.status_code == 200
        data = response.json()
        assert data == []

        self.client.logout()

    def test_roster_application_api_accepts_message(self):
        character = ObjectDB.objects.create(
            db_key="Hero",
            db_typeclass_path="typeclasses.characters.Character",
        )
        roster = Roster.objects.create(name="Active")
        entry = RosterEntry.objects.create(character=character, roster=roster)
        self.client.force_login(self.account)
        url = reverse("roster-apply", args=[entry.id])
        response = self.client.post(url, {"message": "Let me play"})
        assert response.status_code == 204

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
        assert response.status_code == 200
        assert response.json() == [{"value": "Bob", "label": "Bob"}]

    @patch("web.api.views.search_views.AccountDB.get_puppeted_characters")
    def test_room_character_search_respects_display_name(self, mock_puppets):
        room = ObjectDBFactory(
            db_key="hall",
            db_typeclass_path="typeclasses.rooms.Room",
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
        assert response.status_code == 200
        assert response.json() == [{"value": "Masked", "label": "Masked"}]


class EmailVerificationAPITests(TestCase):
    """Tests for custom email verification endpoint."""

    def setUp(self):
        self.url = reverse("api-email-verify")
        self.email_address = EmailAddressFactory(verified=False)

    def test_successful_email_verification(self):
        """Test that a valid confirmation key verifies the email."""
        confirmation = EmailConfirmationFactory(email_address=self.email_address)

        response = self.client.post(
            self.url,
            {"key": confirmation.key},
            content_type="application/json",
        )

        assert response.status_code == 200
        assert response.json()["detail"] == "Email successfully verified"

        self.email_address.refresh_from_db()
        assert self.email_address.verified

        assert not EmailConfirmation.objects.filter(key=confirmation.key).exists()

    def test_email_verification_with_uppercase_key(self):
        """Test that verification works with uppercase keys (lowercased internally)."""
        confirmation = EmailConfirmationFactory(email_address=self.email_address)

        response = self.client.post(
            self.url,
            {"key": confirmation.key.upper()},
            content_type="application/json",
        )

        assert response.status_code == 200
        self.email_address.refresh_from_db()
        assert self.email_address.verified

    def test_email_verification_missing_key(self):
        """Test that request without key returns 400."""
        response = self.client.post(
            self.url,
            {},
            content_type="application/json",
        )

        assert response.status_code == 400
        assert "required" in response.json()["detail"].lower()

    def test_email_verification_invalid_key(self):
        """Test that an invalid key returns 400."""
        response = self.client.post(
            self.url,
            {"key": "invalid-key-that-does-not-exist"},
            content_type="application/json",
        )

        assert response.status_code == 400
        assert "invalid" in response.json()["detail"].lower()

    def test_email_verification_already_verified(self):
        """Test that verifying an already-verified email returns 400."""
        verified_email = EmailAddressFactory(verified=True)
        confirmation = EmailConfirmationFactory(email_address=verified_email)

        response = self.client.post(
            self.url,
            {"key": confirmation.key},
            content_type="application/json",
        )

        assert response.status_code == 400
        assert "already verified" in response.json()["detail"].lower()

    def test_email_verification_expired_key(self):
        """Test that an expired key returns 400."""
        old_time = timezone.now() - timezone.timedelta(days=4)
        confirmation = EmailConfirmationFactory(
            email_address=self.email_address,
            sent=old_time,
        )

        response = self.client.post(
            self.url,
            {"key": confirmation.key},
            content_type="application/json",
        )

        assert response.status_code == 400
        assert "expired" in response.json()["detail"].lower()

    def test_email_verification_expired_key_with_null_sent(self):
        """Test expiration check when sent field is None (uses created instead)."""
        old_time = timezone.now() - timezone.timedelta(days=4)
        confirmation = EmailConfirmationFactory(
            email_address=self.email_address,
            sent=timezone.now(),
        )
        confirmation.created = old_time
        confirmation.sent = None
        confirmation.save()

        response = self.client.post(
            self.url,
            {"key": confirmation.key},
            content_type="application/json",
        )

        assert response.status_code == 400
        assert "expired" in response.json()["detail"].lower()
