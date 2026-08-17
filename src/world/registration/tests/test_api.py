"""Tests for the staff invite ViewSet + public registration-status endpoint (#3054)."""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.registration.factories import AccountInviteFactory
from world.registration.models import AccountInvite, get_registration_config


class RegistrationStatusViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/api/registration/status/"

    def test_status_reports_closed_by_default(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"open": False})

    def test_status_reports_open_when_flipped(self):
        config = get_registration_config()
        config.registration_open = True
        config.save(update_fields=["registration_open"])

        response = self.client.get(self.url)
        self.assertEqual(response.data, {"open": True})

    def test_status_is_publicly_reachable_anonymously(self):
        response = self.client.get(self.url)
        self.assertNotEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertNotEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class AccountInviteViewSetPermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(username="invite_api_staff", is_staff=True)
        cls.player = AccountFactory(username="invite_api_player", is_staff=False)

    def setUp(self):
        self.client = APIClient()
        self.list_url = "/api/staff/invites/"

    def test_anonymous_cannot_list(self):
        response = self.client.get(self.list_url)
        self.assertIn(
            response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
        )

    def test_player_cannot_list(self):
        self.client.force_authenticate(self.player)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_can_list(self):
        self.client.force_authenticate(self.staff)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_player_cannot_issue(self):
        self.client.force_authenticate(self.player)
        response = self.client.post(self.list_url, {"email": "nope@example.com"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_cannot_issue(self):
        response = self.client.post(self.list_url, {"email": "nope@example.com"}, format="json")
        self.assertIn(
            response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
        )


class AccountInviteViewSetJourneyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(username="invite_journey_staff", is_staff=True)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.staff)
        self.list_url = "/api/staff/invites/"

    def test_issue_invite(self):
        response = self.client.post(
            self.list_url, {"email": "issued@example.com", "note": "friend"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["email"], "issued@example.com")
        self.assertEqual(response.data["status"], "pending")
        self.assertTrue(AccountInvite.objects.filter(email="issued@example.com").exists())

    def test_issue_invite_dedups_active_invite(self):
        first = self.client.post(self.list_url, {"email": "dup@example.com"}, format="json")
        second = self.client.post(self.list_url, {"email": "dup@example.com"}, format="json")
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(AccountInvite.objects.filter(email="dup@example.com").count(), 1)

    def test_list_invites(self):
        AccountInviteFactory(invited_by=self.staff, email="listed@example.com")
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        emails = [row["email"] for row in response.data["results"]]
        self.assertIn("listed@example.com", emails)

    def test_filter_by_status(self):
        AccountInviteFactory(invited_by=self.staff, email="pending@example.com")
        revoked = AccountInviteFactory(invited_by=self.staff, email="dead@example.com")
        revoked.revoked_at = revoked.created_at
        revoked.save(update_fields=["revoked_at"])

        response = self.client.get(self.list_url, {"status": "revoked"})
        emails = [row["email"] for row in response.data["results"]]
        self.assertIn("dead@example.com", emails)
        self.assertNotIn("pending@example.com", emails)

    def test_revoke_invite(self):
        invite = AccountInviteFactory(invited_by=self.staff, email="revoke-me@example.com")
        response = self.client.post(f"{self.list_url}{invite.pk}/revoke/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        invite.refresh_from_db()
        self.assertIsNotNone(invite.revoked_at)
        self.assertEqual(response.data["status"], "revoked")


class VerificationLinkViewTests(TestCase):
    """Staff copy a verification link when mail cannot reach the invitee (#3193)."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(username="verify_link_staff", is_staff=True)
        cls.player = AccountFactory(username="verify_link_player", is_staff=False)

    def setUp(self):
        self.client = APIClient()
        self.url = "/api/staff/verification-link/"
        self.client.force_authenticate(self.staff)

    def _make_unverified(self, email: str):
        from allauth.account.models import EmailAddress

        account = AccountFactory(username=f"unverified_{email.split('@')[0]}", email=email)
        return EmailAddress.objects.create(user=account, email=email, verified=False, primary=True)

    def test_player_cannot_generate(self):
        self.client.force_authenticate(self.player)
        response = self.client.post(self.url, {"email": "someone@example.com"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unknown_email_is_404(self):
        response = self.client.post(self.url, {"email": "nobody@example.com"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_verified_email_is_400(self):
        from allauth.account.models import EmailAddress

        account = AccountFactory(username="already_verified", email="done@example.com")
        EmailAddress.objects.create(
            user=account, email="done@example.com", verified=True, primary=True
        )
        response = self.client.post(self.url, {"email": "done@example.com"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_returns_link_whose_key_resolves(self):
        """The returned link embeds an HMAC key allauth accepts for this address."""
        from allauth.account.models import EmailConfirmationHMAC

        address = self._make_unverified("locked-out@example.com")
        response = self.client.post(self.url, {"email": "locked-out@example.com"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        link = response.data["link"]
        self.assertIn("/verify-email/", link)
        key = link.rstrip("/").rsplit("/", 1)[-1]
        confirmation = EmailConfirmationHMAC.from_key(key)
        self.assertIsNotNone(confirmation)
        self.assertEqual(confirmation.email_address.pk, address.pk)

    def test_lookup_is_case_insensitive(self):
        self._make_unverified("mixedcase@example.com")
        response = self.client.post(self.url, {"email": "MixedCase@example.com"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
