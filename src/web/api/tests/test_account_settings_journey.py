"""Account settings journeys at the real allauth headless endpoints (#3591).

These are the URLs the React Account tab posts to. Mirrors
``world/registration/tests/test_signup_journey.py``: ``APIClient`` against the
mounted routes, never the adapter in isolation.
"""

import re
import time
from unittest.mock import patch
from urllib.parse import unquote, unquote_plus

from allauth.account.models import EmailAddress
from allauth.mfa.models import Authenticator
from allauth.mfa.totp.internal import auth as totp_auth
from django.core import mail
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from evennia_extensions.models import PlayerData

BASE = "/api/auth/browser/v1"
PASSWORD = "JourneyPass123!"  # noqa: S105 - test fixture value, not a real secret
NEW_PASSWORD = "JourneyPass456!"  # noqa: S105 - test fixture value, not a real secret


def current_totp_code(secret: str) -> str:
    counter = int(time.time()) // 30
    return totp_auth.format_hotp_value(totp_auth.hotp_value(secret, counter))


class _JourneyBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory(username="journey_user", email="journey@example.com")
        cls.account.set_password(PASSWORD)
        cls.account.save()
        PlayerData.objects.get_or_create(account=cls.account)
        EmailAddress.objects.create(
            user=cls.account, email="journey@example.com", primary=True, verified=True
        )

    def setUp(self):
        self.client = APIClient()
        mail.outbox = []

    def login(self, password=PASSWORD):
        return self.client.post(
            f"{BASE}/auth/login",
            {"username": "journey_user", "password": password},
            format="json",
        )


class PasswordChangeJourneyTests(_JourneyBase):
    def test_wrong_current_password_is_400(self):
        self.assertEqual(self.login().status_code, status.HTTP_200_OK)
        response = self.client.post(
            f"{BASE}/account/password/change",
            {"current_password": "nope", "new_password": NEW_PASSWORD},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json()["errors"][0]["param"], "current_password")

    def test_change_keeps_the_session_and_mails_a_notice(self):
        self.login()
        response = self.client.post(
            f"{BASE}/account/password/change",
            {"current_password": PASSWORD, "new_password": NEW_PASSWORD},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.json()["meta"]["is_authenticated"])
        self.assertIsNotNone(self.client.get("/api/user/").json())
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("password", mail.outbox[0].subject.lower())
        fresh = APIClient()
        self.assertEqual(
            fresh.post(
                f"{BASE}/auth/login",
                {"username": "journey_user", "password": PASSWORD},
                format="json",
            ).status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            fresh.post(
                f"{BASE}/auth/login",
                {"username": "journey_user", "password": NEW_PASSWORD},
                format="json",
            ).status_code,
            status.HTTP_200_OK,
        )


class EmailChangeJourneyTests(_JourneyBase):
    def test_change_is_pending_until_verified_then_swaps(self):
        self.login()
        response = self.client.post(
            f"{BASE}/account/email", {"email": "new@example.com"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        addresses = {a["email"]: a for a in response.json()["data"]}
        self.assertTrue(addresses["journey@example.com"]["primary"])
        self.assertFalse(addresses["new@example.com"]["verified"])
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["new@example.com"])
        # The mail body URL-encodes the key (the ":" separators become "%3A");
        # the custom verify view expects the raw signed key, so unquote first.
        key = unquote(re.search(r"/verify-email/([^\s/]+)", mail.outbox[0].body).group(1))
        # The existing custom verify view (general_views.EmailVerificationAPIView).
        verify = self.client.post(f"{BASE}/auth/email/verify", {"key": key}, format="json")
        self.assertEqual(verify.status_code, status.HTTP_200_OK)
        listing = self.client.get(f"{BASE}/account/email").json()["data"]
        self.assertEqual([a["email"] for a in listing], ["new@example.com"])
        self.assertTrue(listing[0]["primary"] and listing[0]["verified"])
        self.assertEqual(self.client.get("/api/user/").json()["email"], "new@example.com")
        # email_changed notice goes to the OLD address.
        self.assertTrue(any(m.to == ["journey@example.com"] for m in mail.outbox[1:]))

    def test_resend_and_cancel_pending(self):
        self.login()
        self.client.post(f"{BASE}/account/email", {"email": "new@example.com"}, format="json")
        mail.outbox = []
        # RATE_LIMITS builds its defaults from the base dict and only overrides
        # keys present in it (allauth.account.app_settings.AppSettings.RATE_LIMITS),
        # so an empty override leaves the "confirm_email" cooldown (default 180s)
        # in place and the immediate resend below hits it. Disable that one key.
        with override_settings(ACCOUNT_RATE_LIMITS={"confirm_email": None}):
            resend = self.client.put(
                f"{BASE}/account/email", {"email": "new@example.com"}, format="json"
            )
        self.assertEqual(resend.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)
        cancel = self.client.delete(
            f"{BASE}/account/email", {"email": "new@example.com"}, format="json"
        )
        self.assertEqual(cancel.status_code, status.HTTP_200_OK)
        self.assertEqual([a["email"] for a in cancel.json()["data"]], ["journey@example.com"])


class ReauthenticationJourneyTests(_JourneyBase):
    def test_stale_session_gets_the_reauth_challenge_then_succeeds(self):
        self.login()
        stale = time.time() + 600  # past ACCOUNT_REAUTHENTICATION_TIMEOUT (300s)
        with patch("allauth.account.internal.flows.reauthentication.time.time", return_value=stale):
            response = self.client.post(
                f"{BASE}/account/email", {"email": "later@example.com"}, format="json"
            )
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
            flows = {f["id"] for f in response.json()["data"]["flows"]}
            self.assertIn("reauthenticate", flows)
            # allauth mounts reauthenticate under auth/, not account/ (headless
            # account/urls.py: auth_patterns, not account_patterns).
            reauth = self.client.post(
                f"{BASE}/auth/reauthenticate", {"password": PASSWORD}, format="json"
            )
            self.assertEqual(reauth.status_code, status.HTTP_200_OK)
        retry = self.client.post(
            f"{BASE}/account/email", {"email": "later@example.com"}, format="json"
        )
        self.assertEqual(retry.status_code, status.HTTP_200_OK)


class TwoFactorJourneyTests(_JourneyBase):
    def _enrol(self) -> str:
        setup = self.client.get(f"{BASE}/account/authenticators/totp")
        self.assertEqual(setup.status_code, status.HTTP_404_NOT_FOUND)
        secret = setup.json()["meta"]["secret"]
        totp_url = setup.json()["meta"]["totp_url"]
        self.assertIn("otpauth://totp/", totp_url)
        # allauth encodes the issuer's space with "+" (query-string form), not
        # "%20"; unquote_plus (not unquote) turns "+" into the space too.
        self.assertIn("Arx II", unquote_plus(totp_url))
        activate = self.client.post(
            f"{BASE}/account/authenticators/totp",
            {"code": current_totp_code(secret)},
            format="json",
        )
        self.assertEqual(activate.status_code, status.HTTP_200_OK)
        return secret

    def test_enrol_login_challenge_code_and_recovery_code(self):
        self.login()
        secret = self._enrol()
        types = {
            a["type"] for a in self.client.get(f"{BASE}/account/authenticators").json()["data"]
        }
        self.assertEqual(types, {"totp", "recovery_codes"})
        codes = self.client.get(f"{BASE}/account/authenticators/recovery-codes").json()["data"]
        self.assertEqual(codes["unused_code_count"], 10)
        recovery_code = codes["unused_codes"][0]
        # Stored secret is ciphertext, not the base32 secret.
        row = Authenticator.objects.get(user=self.account, type=Authenticator.Type.TOTP)
        self.assertNotEqual(row.data["secret"], secret)

        self.client.delete(f"{BASE}/auth/session")
        login = self.login()
        self.assertEqual(login.status_code, status.HTTP_401_UNAUTHORIZED)
        pending = [f for f in login.json()["data"]["flows"] if f.get("is_pending")]
        self.assertEqual(pending[0]["id"], "mfa_authenticate")
        # DRF's Response.rendered_content drops the Content-Type header when the
        # rendered body is empty (data=None renders to b""), so .json() raises
        # on the test client here; read .data instead (see rest_framework's
        # response.py: `if not ret: del self['Content-Type']`).
        self.assertIsNone(self.client.get("/api/user/").data)

        wrong = self.client.post(f"{BASE}/auth/2fa/authenticate", {"code": "000000"}, format="json")
        self.assertEqual(wrong.status_code, status.HTTP_400_BAD_REQUEST)
        ok = self.client.post(
            f"{BASE}/auth/2fa/authenticate", {"code": current_totp_code(secret)}, format="json"
        )
        self.assertEqual(ok.status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get("/api/user/").json()["username"], "journey_user")

        self.client.delete(f"{BASE}/auth/session")
        self.login()
        via_recovery = self.client.post(
            f"{BASE}/auth/2fa/authenticate", {"code": recovery_code}, format="json"
        )
        self.assertEqual(via_recovery.status_code, status.HTTP_200_OK)
        remaining = self.client.get(f"{BASE}/account/authenticators/recovery-codes").json()["data"]
        self.assertEqual(remaining["unused_code_count"], 9)

    def test_disable_removes_both_authenticators(self):
        self.login()
        self._enrol()
        response = self.client.delete(f"{BASE}/account/authenticators/totp")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(Authenticator.objects.filter(user=self.account).exists())

    def test_pending_email_change_does_not_block_enrolment(self):
        """MFA_ALLOW_UNVERIFIED_EMAIL lifts allauth's interlock (risk 3)."""
        self.login()
        self.client.post(f"{BASE}/account/email", {"email": "new@example.com"}, format="json")
        self._enrol()

    def test_2fa_account_can_still_change_email(self):
        self.login()
        self._enrol()
        response = self.client.post(
            f"{BASE}/account/email", {"email": "after2fa@example.com"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
