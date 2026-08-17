"""Journey tests at the real headless signup endpoint (#3054).

Mirrors ``web/api/tests/test_registration_verification_flow.py``'s pattern
of hitting ``/api/auth/browser/v1/auth/signup`` directly through
``APIClient`` — this is the highest seam named in the spec's Test seams
section, proving the adapter gate actually wires into the endpoint the
React signup form posts to (not just the adapter method in isolation).
"""

from datetime import timedelta
import json
from unittest.mock import patch

from allauth.account.adapter import DefaultAccountAdapter
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.registration.factories import AccountInviteFactory
from world.registration.models import AccountInvite, AccountMailFailure, get_registration_config

User = get_user_model()


class SignupJourneyTests(TestCase):
    """Closed-by-default registration gate, exercised through the real endpoint."""

    def setUp(self):
        self.client = APIClient()
        self.signup_url = "/api/auth/browser/v1/auth/signup"
        self.staff = AccountFactory(username="signup_journey_staff", is_staff=True)

    def _signup(self, *, username: str, email: str, invite_token: str | None = None) -> object:
        payload = {"username": username, "email": email, "password": "TestPass123!"}
        if invite_token is not None:
            payload["invite_token"] = invite_token
        response = self.client.post(self.signup_url, payload, format="json")
        response._json_body = json.loads(response.content) if response.content else {}
        return response

    def test_closed_with_no_invite_is_rejected(self):
        self.assertFalse(get_registration_config().registration_open)

        response = self._signup(username="no_invite_user", email="no-invite@example.com")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(User.objects.filter(username="no_invite_user").exists())

    def test_closed_with_valid_invite_and_matching_email_creates_account(self):
        invite = AccountInviteFactory(invited_by=self.staff, email="matched@example.com")

        response = self._signup(
            username="matched_user", email="matched@example.com", invite_token=invite.token
        )

        # ACCOUNT_EMAIL_VERIFICATION=mandatory -> 401 with a pending verify_email flow
        # on successful signup (same shape the existing verification-flow test asserts).
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertTrue(User.objects.filter(username="matched_user").exists())

        invite.refresh_from_db()
        self.assertIsNotNone(invite.redeemed_at)
        account = User.objects.get(username="matched_user")
        self.assertEqual(invite.redeemed_by_id, account.id)

    def test_closed_with_valid_invite_and_different_email_is_rejected(self):
        invite = AccountInviteFactory(invited_by=self.staff, email="matched@example.com")

        response = self._signup(
            username="mismatched_user",
            email="different@example.com",
            invite_token=invite.token,
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(User.objects.filter(username="mismatched_user").exists())
        invite.refresh_from_db()
        self.assertIsNone(invite.redeemed_at)

    def test_open_registration_allows_plain_signup(self):
        config = get_registration_config()
        config.registration_open = True
        config.save(update_fields=["registration_open"])

        response = self._signup(username="open_user", email="open@example.com")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertTrue(User.objects.filter(username="open_user").exists())

    def test_mail_failure_does_not_fail_signup(self):
        """A dead mail provider must not turn a successful signup into a 500 (#3193).

        Patches the parent adapter's send_mail (the seam under
        ArxAccountAdapter's catch) with the exact failure from the 2026-08-16
        outage. Signup must still return the normal pending-verification shape,
        the account must exist, and the failure must be recorded staff-visibly.
        """
        config = get_registration_config()
        config.registration_open = True
        config.save(update_fields=["registration_open"])

        with patch.object(
            DefaultAccountAdapter,
            "send_mail",
            side_effect=TimeoutError("[Errno 110] Connection timed out"),
        ):
            response = self._signup(username="mail_down_user", email="mail-down@example.com")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertTrue(User.objects.filter(username="mail_down_user").exists())

        failure = AccountMailFailure.objects.get(email="mail-down@example.com")
        self.assertIn("TimeoutError", failure.error)
        self.assertIn("Connection timed out", failure.error)

    def test_reused_invite_is_rejected(self):
        invite = AccountInviteFactory(invited_by=self.staff, email="reused@example.com")

        first = self._signup(
            username="reused_user_one", email="reused@example.com", invite_token=invite.token
        )
        self.assertEqual(first.status_code, status.HTTP_401_UNAUTHORIZED)

        second = self._signup(
            username="reused_user_two", email="reused@example.com", invite_token=invite.token
        )
        self.assertEqual(second.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(User.objects.filter(username="reused_user_two").exists())

    def test_expired_invite_is_rejected_with_same_neutral_message(self):
        expired = AccountInviteFactory(
            invited_by=self.staff,
            email="expired@example.com",
            expires_at=timezone.now() - timedelta(days=1),
        )
        no_invite_response = self._signup(
            username="no_invite_neutral_user", email="never-invited@example.com"
        )
        expired_response = self._signup(
            username="expired_user", email="expired@example.com", invite_token=expired.token
        )

        self.assertEqual(no_invite_response.status_code, expired_response.status_code)
        self.assertEqual(
            no_invite_response._json_body, expired_response._json_body
        )  # same neutral body

    def test_revoked_invite_is_rejected_with_same_neutral_message(self):
        revoked = AccountInviteFactory(
            invited_by=self.staff, email="revoked@example.com", revoked_at=timezone.now()
        )
        no_invite_response = self._signup(
            username="no_invite_neutral_user2", email="never-invited2@example.com"
        )
        revoked_response = self._signup(
            username="revoked_user", email="revoked@example.com", invite_token=revoked.token
        )

        self.assertEqual(no_invite_response.status_code, revoked_response.status_code)
        self.assertEqual(no_invite_response._json_body, revoked_response._json_body)

    def test_account_invite_survives_and_is_queryable_after_journey(self):
        """Sanity check the invite row itself is untouched by a rejected attempt."""
        invite = AccountInviteFactory(invited_by=self.staff, email="untouched@example.com")
        self._signup(
            username="wrong_email_probe", email="probe@example.com", invite_token=invite.token
        )
        self.assertTrue(
            AccountInvite.objects.filter(pk=invite.pk, redeemed_at__isnull=True).exists()
        )
