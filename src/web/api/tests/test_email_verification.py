"""Tests for email verification endpoints."""

from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

User = get_user_model()


class ResendEmailVerificationTestCase(TestCase):
    """Test cases for the resend email verification endpoint."""

    def setUp(self):
        """Set up test fixtures."""
        self.client = APIClient()
        self.url = "/api/auth/browser/v1/auth/email/request"

        # Create a test user with unverified email
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.email_address = EmailAddress.objects.create(
            user=self.user, email="test@example.com", primary=True, verified=False
        )

        # Clear the test email outbox
        mail.outbox = []

    def test_resend_unauthenticated_with_valid_email(self):
        """Test resending verification email for unauthenticated user with valid email."""
        response = self.client.post(self.url, {"email": "test@example.com"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["detail"], "Verification email sent")

        # Verify that an email was sent
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["test@example.com"])

    def test_resend_unauthenticated_with_nonexistent_email(self):
        """Test resending verification for email that doesn't exist."""
        response = self.client.post(self.url, {"email": "nonexistent@example.com"}, format="json")

        # Should return success to prevent enumeration
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("If an unverified account exists", response.data["detail"])

        # Verify that NO email was sent (anti-enumeration)
        self.assertEqual(len(mail.outbox), 0)

    def test_resend_unauthenticated_with_verified_email(self):
        """Test resending verification for already verified email."""
        # Mark email as verified
        self.email_address.verified = True
        self.email_address.save()

        response = self.client.post(self.url, {"email": "test@example.com"}, format="json")

        # Should return success to prevent enumeration (email is verified, not unverified)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("If an unverified account exists", response.data["detail"])

        # Verify that NO email was sent (already verified)
        self.assertEqual(len(mail.outbox), 0)

    def test_resend_unauthenticated_without_email(self):
        """Test resending verification without providing email."""
        response = self.client.post(self.url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], "Email address is required")

    def test_resend_authenticated_user(self):
        """Test resending verification email for authenticated user."""
        self.client.force_authenticate(user=self.user)
        response = self.client.post(self.url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["detail"], "Verification email sent")

        # Verify that an email was sent
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["test@example.com"])

    def test_resend_authenticated_already_verified(self):
        """Test resending verification for authenticated user with verified email."""
        self.email_address.verified = True
        self.email_address.save()

        self.client.force_authenticate(user=self.user)
        response = self.client.post(self.url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], "Email already verified")

    def test_case_insensitive_email_lookup(self):
        """Test that email lookup is case-insensitive."""
        response = self.client.post(self.url, {"email": "TEST@EXAMPLE.COM"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["detail"], "Verification email sent")

        # Verify that an email was sent
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["test@example.com"])


class EmailVerificationTestCase(TestCase):
    """Test cases for the email verification endpoint."""

    def setUp(self):
        """Set up test fixtures."""
        self.client = APIClient()
        self.verify_url = "/api/auth/browser/v1/auth/email/verify"

        # Create a test user with unverified email
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.email_address = EmailAddress.objects.create(
            user=self.user, email="test@example.com", primary=True, verified=False
        )

        # Generate a verification key
        confirmation = self.email_address.send_confirmation(signup=True)
        self.verification_key = confirmation.key

    def test_verify_with_valid_key(self):
        """Test verifying email with a valid key."""
        response = self.client.post(self.verify_url, {"key": self.verification_key}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["detail"], "Email successfully verified")

        # Verify that email is now marked as verified
        self.email_address.refresh_from_db()
        self.assertTrue(self.email_address.verified)

    def test_verify_with_invalid_key(self):
        """Test verifying email with an invalid key."""
        response = self.client.post(self.verify_url, {"key": "invalid-key-12345"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Invalid or expired", response.data["detail"])

        # Verify that email is still unverified
        self.email_address.refresh_from_db()
        self.assertFalse(self.email_address.verified)

    def test_verify_without_key(self):
        """Test verifying email without providing a key."""
        response = self.client.post(self.verify_url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], "Email confirmation key is required")

    def test_verify_already_verified_email(self):
        """Test verifying an email that's already verified."""
        # Mark email as verified
        self.email_address.verified = True
        self.email_address.save()

        response = self.client.post(self.verify_url, {"key": self.verification_key}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], "Email address is already verified")
