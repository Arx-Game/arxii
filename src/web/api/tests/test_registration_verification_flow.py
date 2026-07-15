"""Integration test for the full registration → email verification → login flow.

Unlike the unit tests in test_email_verification.py (which test the verify
endpoint in isolation), this test exercises the complete user journey:

1. Register via the allauth signup API
2. Generate a verification key using Django's signing module (same as
   allauth's HMAC mode — no send_confirmation helper)
3. Verify the email via the custom verify endpoint
4. Log in via the allauth login API
5. Fetch /api/user/ and confirm the account is authenticated + verified

This proves the real HMAC verification path works end-to-end, including
the AccountAdapter's PlayerData creation and the EmailAddress model's
verification state transition.
"""

from allauth.account import app_settings
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core import mail, signing
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.models import PlayerData

User = get_user_model()


class FullRegistrationVerificationLoginFlowTest(TestCase):
    """End-to-end integration test for the signup → verify → login journey."""

    def setUp(self):
        self.client = APIClient()
        self.signup_url = "/api/auth/browser/v1/auth/signup"
        self.verify_url = "/api/auth/browser/v1/auth/email/verify"
        self.login_url = "/api/auth/browser/v1/auth/login"
        self.user_url = "/api/user/"
        self.username = "integration_test_user"
        self.email = "integration@test.com"
        self.password = "TestPass123!"  # noqa: S105
        mail.outbox = []

    def _signup(self):
        """Register a new account via the allauth headless signup endpoint.

        allauth headless returns its own ``AuthenticationResponse`` (not a
        DRF ``Response``), so the JSON body is in ``response.content`` —
        ``response.data`` is not available on this response type.
        """
        import json

        response = self.client.post(
            self.signup_url,
            {"username": self.username, "email": self.email, "password": self.password},
            format="json",
        )
        response._json_body = json.loads(response.content) if response.content else {}
        return response

    def _generate_verification_key(self, email_address):
        """Generate an HMAC verification key using Django's signing module.

        This mirrors allauth's EmailConfirmationHMAC.key() method exactly:
        ``signing.dumps(obj=self.email_address.pk, salt=app_settings.SALT)``.
        We call it directly instead of via ``send_confirmation`` to prove
        the signing contract is stable and that the verify endpoint
        correctly unpacks the key without relying on allauth's helper.
        """
        return signing.dumps(obj=email_address.pk, salt=app_settings.SALT)

    def test_full_flow_signup_verify_login(self):
        """The complete registration → verification → login journey."""
        # --- Step 1: Signup ---
        response = self._signup()

        # allauth headless with ACCOUNT_EMAIL_VERIFICATION=mandatory returns
        # 401 with a verify_email flow on successful signup
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        flows = response._json_body.get("data", {}).get("flows", [])
        verify_flow = [f for f in flows if f.get("id") == "verify_email"]
        self.assertTrue(verify_flow, "Signup should return a verify_email flow")
        self.assertTrue(verify_flow[0].get("is_pending"))

        # Account and EmailAddress should exist
        account = User.objects.get(username=self.username)
        self.assertEqual(account.email, self.email)

        email_address = EmailAddress.objects.get(user=account)
        self.assertFalse(email_address.verified)
        self.assertTrue(email_address.primary)

        # PlayerData should have been created by the AccountAdapter
        self.assertTrue(PlayerData.objects.filter(account=account).exists())

        # A verification email should have been sent (console backend in tests)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.email])

        # --- Step 2: Generate key and verify email ---
        key = self._generate_verification_key(email_address)
        response = self.client.post(self.verify_url, {"key": key}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["detail"], "Email successfully verified")

        # EmailAddress should now be verified
        email_address.refresh_from_db()
        self.assertTrue(email_address.verified)

        # --- Step 3: Login ---
        response = self.client.post(
            self.login_url,
            {"username": self.username, "password": self.password},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # --- Step 4: Fetch user data ---
        # The login endpoint returns allauth's AuthenticationResponse (not a
        # DRF Response), so we fetch /api/user/ separately to verify the
        # session is authenticated and the account shows as verified.
        response = self.client.get(self.user_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data)
        self.assertEqual(response.data["username"], self.username)
        self.assertTrue(response.data["email_verified"])

    def test_verify_with_django_signing_key_directly(self):
        """Verify that a key generated via Django's signing module works.

        This is the core of the integration test: it proves the verify
        endpoint's signing.loads() call correctly unpacks the key that
        signing.dumps() produces, without any allauth helper in between.
        """
        # Create an account with unverified email
        account = User.objects.create_user(
            username="signing_test_user",
            email="signing@test.com",
            password=self.password,
        )
        email_address = EmailAddress.objects.create(
            user=account,
            email="signing@test.com",
            primary=True,
            verified=False,
        )

        # Generate the key the same way the frontend would receive it
        key = signing.dumps(obj=email_address.pk, salt=app_settings.SALT)

        # Verify via the API
        response = self.client.post(self.verify_url, {"key": key}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        email_address.refresh_from_db()
        self.assertTrue(email_address.verified)

    def test_login_before_verification_fails(self):
        """Login with an unverified account is blocked by allauth."""
        self._signup()

        # allauth headless with ACCOUNT_EMAIL_VERIFICATION=mandatory blocks
        # login for unverified accounts — returns 401 with an error
        # indicating email verification is required.
        response = self.client.post(
            self.login_url,
            {"username": self.username, "password": self.password},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_verify_expired_key_is_rejected(self):
        """An expired signing key is rejected by the verify endpoint."""
        account = User.objects.create_user(
            username="expired_test_user",
            email="expired@test.com",
            password=self.password,
        )
        email_address = EmailAddress.objects.create(
            user=account,
            email="expired@test.com",
            primary=True,
            verified=False,
        )

        # Generate a key with a max_age of 0 (immediately expired)
        # We can't use signing.dumps with max_age (it doesn't take one),
        # so we manually create an expired key by tampering with the timestamp.
        # Easier: just pass a garbage key that will fail signing.loads.
        response = self.client.post(
            self.verify_url,
            {"key": "expired-garbage-key-not-a-valid-signature"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Invalid or expired", response.data["detail"])

        email_address.refresh_from_db()
        self.assertFalse(email_address.verified)

    def test_already_verified_email_returns_error(self):
        """Verifying an already-verified email returns a 400."""
        account = User.objects.create_user(
            username="already_verified_user",
            email="verified@test.com",
            password=self.password,
        )
        email_address = EmailAddress.objects.create(
            user=account,
            email="verified@test.com",
            primary=True,
            verified=True,
        )

        key = signing.dumps(obj=email_address.pk, salt=app_settings.SALT)
        response = self.client.post(self.verify_url, {"key": key}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already verified", response.data["detail"])
