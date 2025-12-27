"""Tests to verify unverified users cannot log in."""

from allauth.account.models import EmailAddress
from django.test import TestCase
from django.urls import reverse

from evennia_extensions.factories import AccountFactory, EmailAddressFactory
from web.api.serializers import AccountPlayerSerializer


class AccountSerializerEmailVerifiedTests(TestCase):
    """Test that AccountPlayerSerializer includes email_verified field."""

    def test_serializer_includes_email_verified_for_verified_user(self):
        """Test that email_verified is True for verified users."""
        account = AccountFactory(username="verified_user")
        EmailAddressFactory(
            user=account, email=account.email, verified=True, primary=True
        )

        serializer = AccountPlayerSerializer(account)
        data = serializer.data

        self.assertIn("email_verified", data)
        self.assertTrue(data["email_verified"])

    def test_serializer_includes_email_verified_for_unverified_user(self):
        """Test that email_verified is False for unverified users."""
        account = AccountFactory(username="unverified_user")
        EmailAddressFactory(
            user=account, email=account.email, verified=False, primary=True
        )

        serializer = AccountPlayerSerializer(account)
        data = serializer.data

        self.assertIn("email_verified", data)
        self.assertFalse(data["email_verified"])

    def test_serializer_email_verified_false_when_no_email_address(self):
        """Test that email_verified defaults to False when no EmailAddress exists."""
        account = AccountFactory(username="no_email_user")
        # Don't create EmailAddress

        serializer = AccountPlayerSerializer(account)
        data = serializer.data

        self.assertIn("email_verified", data)
        self.assertFalse(data["email_verified"])


class UnverifiedUserLoginBlockingTests(TestCase):
    """Test that unverified users are blocked from logging in."""

    def test_unverified_user_cannot_login(self):
        """Test that login fails for unverified users.

        When ACCOUNT_EMAIL_VERIFICATION='mandatory'.
        """
        # Create account with unverified email
        account = AccountFactory(username="unverified_user", password="testpass123")
        EmailAddressFactory(user=account, email=account.email, verified=False)

        # Attempt to login via allauth headless API
        url = reverse("headless:browser:account:login")
        response = self.client.post(
            url,
            {"username": "unverified_user", "password": "testpass123"},
            content_type="application/json",
        )

        # Should be rejected (401 or 400)
        self.assertIn(response.status_code, [400, 401])

        # Should indicate email verification required
        data = response.json()
        # Allauth headless returns flows when email verification is needed
        if response.status_code == 401:
            self.assertIn("flows", data.get("data", {}))
            flows = data["data"]["flows"]
            # Should have a verify_email flow that is pending
            verify_flow = next(
                (f for f in flows if f.get("id") == "verify_email"), None
            )
            self.assertIsNotNone(verify_flow, "Should have verify_email flow")
            self.assertTrue(
                verify_flow.get("is_pending"), "verify_email flow should be pending"
            )

    def test_verified_user_can_login(self):
        """Test that login succeeds for verified users."""
        # Create account with verified email
        account = AccountFactory(username="verified_user", password="testpass123")
        EmailAddressFactory(user=account, email=account.email, verified=True)

        # Attempt to login via allauth headless API
        url = reverse("headless:browser:account:login")
        response = self.client.post(
            url,
            {"username": "verified_user", "password": "testpass123"},
            content_type="application/json",
        )

        # Should succeed
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("user", data.get("data", {}))

    def test_user_verification_status_in_api(self):
        """Test that we can check if a user's email is verified."""
        account = AccountFactory(username="test_status")
        email_address = EmailAddressFactory(
            user=account,
            email=account.email,
            verified=False,
        )

        # Check database state
        self.assertFalse(email_address.verified)

        # Verify email
        email_address.verified = True
        email_address.save()

        # Check state changed
        email_address.refresh_from_db()
        self.assertTrue(email_address.verified)

    def test_account_has_email_addresses(self):
        """Test that we can query a user's email addresses and verification status."""
        account = AccountFactory(username="multi_email")

        # Add multiple email addresses
        EmailAddressFactory(
            user=account,
            email="primary@test.com",
            verified=True,
            primary=True,
        )
        EmailAddressFactory(
            user=account,
            email="secondary@test.com",
            verified=False,
            primary=False,
        )

        # Query email addresses
        email_addresses = EmailAddress.objects.filter(user=account)
        self.assertEqual(email_addresses.count(), 2)

        # Check primary verified email
        primary_email = email_addresses.get(primary=True)
        self.assertTrue(primary_email.verified)
        self.assertEqual(primary_email.email, "primary@test.com")

        # Check secondary unverified email
        secondary_email = email_addresses.get(primary=False)
        self.assertFalse(secondary_email.verified)
