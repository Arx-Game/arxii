"""Recover an invited account through the real headless endpoints."""

import re

from allauth.account.models import EmailAddress, EmailConfirmationHMAC
from django.conf import settings
from django.core import mail
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.registration.factories import AccountInviteFactory


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class PasswordRecoveryJourneyTests(TestCase):
    """A forgotten password does not strand a freshly invited player."""

    def test_invite_verify_recover_then_login(self):
        client = APIClient()
        staff = AccountFactory(is_staff=True)
        email = "recovery-journey@example.com"
        invite = AccountInviteFactory(invited_by=staff, email=email)
        response = client.post(
            "/api/auth/browser/v1/auth/signup",
            {
                "username": "recovery_journey",
                "email": email,
                "password": "OriginalJourneyPass947!",
                "invite_token": invite.token,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 401, response.content)
        address = EmailAddress.objects.get(email=email)
        response = client.post(
            "/api/auth/browser/v1/auth/email/verify",
            {"key": EmailConfirmationHMAC(address).key},
            format="json",
        )
        self.assertIn(response.status_code, (200, 401))
        address.refresh_from_db()
        self.assertTrue(address.verified)

        # A new browser proves the link works without the signup session.
        client = APIClient()
        response = client.post(
            "/api/auth/browser/v1/auth/password/request", {"email": email}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        reset_mail = mail.outbox[-1]
        self.assertIn(email, reset_mail.to)
        match = re.search(r"/reset-password/([A-Za-z0-9:-]+)", reset_mail.body)
        self.assertIsNotNone(match, reset_mail.body)
        key = match.group(1)
        url = "/api/auth/browser/v1/auth/password/reset"
        self.assertEqual(client.get(url, HTTP_X_PASSWORD_RESET_KEY=key).status_code, 200)
        self.assertEqual(
            client.post(url, {"key": key, "password": "123"}, format="json").status_code,
            400,
        )
        response = client.post(url, {"key": key, "password": "LanternMeadow!853"}, format="json")
        self.assertEqual(response.status_code, 401, response.content)
        self.assertIn({"id": "login"}, response.json()["data"]["flows"])
        self.assertEqual(client.get(url, HTTP_X_PASSWORD_RESET_KEY=key).status_code, 400)
        user = address.user
        user.refresh_from_db()
        self.assertFalse(user.check_password("OriginalJourneyPass947!"))
        self.assertTrue(user.check_password("LanternMeadow!853"))

        for identity in ({"username": "recovery_journey"}, {"email": email}):
            client = APIClient()
            response = client.post(
                "/api/auth/browser/v1/auth/login",
                {**identity, "password": "LanternMeadow!853"},
                format="json",
            )
            self.assertEqual(response.status_code, 200, response.content)
            self.assertEqual(client.get("/api/user/").status_code, 200)
        invite.refresh_from_db()
        self.assertIsNotNone(invite.redeemed_at)
        self.assertEqual(user.db_typeclass_path, settings.BASE_ACCOUNT_TYPECLASS)

    def test_unknown_address_has_the_same_request_response(self):
        client = APIClient()
        response = client.post(
            "/api/auth/browser/v1/auth/password/request",
            {"email": "no-such-recovery-account@example.com"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("user", response.json().get("data", {}))
