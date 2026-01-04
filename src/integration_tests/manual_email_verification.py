"""
Email Verification Integration Tests

⚠️ MANUAL TESTING REQUIRED - DO NOT RUN AUTOMATICALLY ⚠️

This file contains integration tests for the email verification flow.
These tests require manual steps and external service setup.

PREREQUISITES:
1. Valid RESEND_API_KEY in src/.env
2. ngrok tunnel running (or publicly accessible server)
3. FRONTEND_URL and CSRF_TRUSTED_ORIGINS set to ngrok URL
4. Both backend and frontend servers running

HUMAN-IN-THE-LOOP STEPS:
- Checking email inbox (Resend dashboard or actual inbox)
- Clicking verification links in emails
- Verifying frontend UI behavior
- Confirming database state changes

This test file serves as a MANUAL TESTING CHECKLIST rather than
automated tests. Follow the steps below in order.
"""

from django.conf import settings
from django.test import TestCase

# NOTE: These are not real automated tests - they are documented manual test steps


class EmailVerificationIntegrationChecklist(TestCase):
    """
    Manual testing checklist for email verification.

    DO NOT RUN WITH: arx test integration_tests

    Instead, use this as a guide for manual testing.
    """

    def test_setup_verification(self):
        """
        MANUAL STEP 1: Verify Environment Setup

        Human checklist:
        [ ] Check that RESEND_API_KEY is set in src/.env
        [ ] Verify RESEND_API_KEY is valid (starts with 're_')
        [ ] Confirm DEFAULT_FROM_EMAIL is set
        [ ] Check that ngrok is installed: `ngrok version`

        Automated check (run this test to verify config):
        """
        assert settings.EMAIL_HOST_PASSWORD is not None, "RESEND_API_KEY not set in .env"
        assert settings.EMAIL_BACKEND.endswith(
            "smtp.EmailBackend"
        ) or settings.EMAIL_BACKEND.endswith("console.EmailBackend"), (
            "EMAIL_BACKEND not configured properly"
        )

    def test_ngrok_setup(self):
        """
        MANUAL STEP 2: Set Up ngrok Tunnel

        Human steps:
        1. Open a new terminal
        2. Run: ngrok http 3000
        3. Copy the HTTPS forwarding URL (e.g., https://abc123.ngrok-free.app)
        4. Update src/.env:
           FRONTEND_URL=https://abc123.ngrok-free.app
           CSRF_TRUSTED_ORIGINS=https://abc123.ngrok-free.app
        5. Restart Django server to pick up new .env settings

        [ ] ngrok tunnel is running
        [ ] FRONTEND_URL updated in .env
        [ ] CSRF_TRUSTED_ORIGINS updated in .env
        [ ] Django server restarted
        [ ] Frontend dev server is running (pnpm dev)

        Automated check:
        """
        try:
            frontend_url = settings.FRONTEND_URL
        except AttributeError:
            frontend_url = None
        assert frontend_url is not None, "FRONTEND_URL not set in settings"
        # Note: We can't automatically verify ngrok is running

    def test_registration_flow(self):
        """
        MANUAL STEP 3: Test User Registration

        Human steps:
        1. Open browser to ngrok URL (e.g., https://abc123.ngrok-free.app)
        2. Click "Register" or navigate to /register
        3. Fill out registration form:
           - Username: test_user_<timestamp>
           - Email: your_real_email@example.com (use a real email you can check)
           - Password: TestPassword123!
           - Confirm Password: TestPassword123!
        4. Submit the form
        5. Verify redirect to "Check Your Email" page

        Expected behavior:
        [ ] Registration form submits successfully
        [ ] Redirected to /register/verify-email
        [ ] See "Check Your Email" message
        [ ] No error messages displayed

        If using console backend (no RESEND_API_KEY):
        [ ] Check Django console for email output
        [ ] Copy verification link from console output

        If using Resend:
        [ ] Check Resend dashboard (https://resend.com/emails)
        [ ] Verify email was sent
        [ ] Check your email inbox
        [ ] Verify email received with verification link
        """
        # This is a manual test - no automated assertions

    def test_email_verification_link(self):
        """
        MANUAL STEP 4: Click Verification Link

        Human steps:
        1. Open the verification email
        2. Click the verification link
           Format: https://abc123.ngrok-free.app/verify-email/<KEY>
        3. Observe the verification page behavior

        Expected behavior:
        [ ] Link opens in browser
        [ ] See "Verifying Your Email" spinner briefly
        [ ] See "Email Verified!" success message
        [ ] See green checkmark icon
        [ ] See "Continue to Login" button
        [ ] Auto-redirect to login after 2 seconds

        Database verification (run in Django shell):
        ```python
        from allauth.account.models import EmailAddress
        email = EmailAddress.objects.get(email='your_email@example.com')
        print(f"Verified: {email.verified}")  # Should be True
        ```
        """

    def test_login_after_verification(self):
        """
        MANUAL STEP 5: Test Login with Verified Account

        Human steps:
        1. Navigate to /login (or wait for auto-redirect)
        2. Enter credentials:
           - Username or Email: test_user_<timestamp>
           - Password: TestPassword123!
        3. Submit login form

        Expected behavior:
        [ ] Login succeeds
        [ ] Redirected to home page (/)
        [ ] User is logged in (see username in header/nav)
        [ ] No email verification warnings
        """

    def test_resend_verification_email(self):
        """
        MANUAL STEP 6: Test Resend Verification Email

        Human steps:
        1. Create a new account (follow test_registration_flow steps)
        2. On "Check Your Email" page (/register/verify-email)
        3. Click "Resend Verification Email" button
        4. Verify button shows "Sending..." state
        5. Verify success message appears

        Expected behavior:
        [ ] Button disables while sending
        [ ] Success message: "Verification email resent successfully!"
        [ ] Second email received (check inbox or Resend dashboard)
        [ ] Second verification link works (click to verify)

        Edge case testing:
        [ ] Click resend multiple times (should not spam)
        [ ] First link still works after resending
        [ ] Second link also works
        """

    def test_expired_verification_link(self):
        """
        MANUAL STEP 7: Test Expired Verification Link

        This test requires modifying the database to simulate an expired link.

        Human steps:
        1. Create a new account
        2. Get the verification key from email/console
        3. Run in Django shell:
           ```python
           from allauth.account.models import EmailConfirmation
           from django.utils import timezone
           import datetime

           conf = EmailConfirmation.objects.latest('created')
           conf.sent = timezone.now() - datetime.timedelta(days=4)
           conf.save()
           ```
        4. Click the verification link

        Expected behavior:
        [ ] Shows "Verification Failed" page
        [ ] Error message: "Email confirmation key has expired"
        [ ] Shows "Resend Verification Email" button
        [ ] Shows "Back to Registration" link
        """

    def test_invalid_verification_link(self):
        """
        MANUAL STEP 8: Test Invalid Verification Link

        Human steps:
        1. Manually construct an invalid verification URL:
           https://abc123.ngrok-free.app/verify-email/invalid-key-12345
        2. Navigate to this URL

        Expected behavior:
        [ ] Shows "Verification Failed" page
        [ ] Error message mentions invalid or expired link
        [ ] Shows "Resend Verification Email" button
        [ ] Shows "Back to Registration" link
        """

    def test_unverified_user_login_blocked(self):
        """
        MANUAL STEP 9: Test Login Block for Unverified Users

        Human steps:
        1. Create a new account (don't click verification link)
        2. Attempt to log in with username and password

        Expected behavior:
        [ ] Login is rejected
        [ ] Error message indicates email verification required
        [ ] Link/button to resend verification email

        Note: This behavior depends on ACCOUNT_EMAIL_VERIFICATION = "mandatory"
        """

    def test_cleanup(self):
        """
        MANUAL STEP 10: Clean Up Test Data

        Human steps:
        1. Delete test accounts from database:
           ```python
           from evennia.accounts.models import AccountDB
           AccountDB.objects.filter(username__startswith='test_user_').delete()
           ```
        2. Stop ngrok tunnel (Ctrl+C in ngrok terminal)
        3. Optionally restore .env to localhost settings

        [ ] Test accounts deleted
        [ ] ngrok tunnel stopped
        [ ] .env restored (if needed)
        """


# Automated helper to verify configuration
class EmailConfigurationTest(TestCase):
    """
    Automated tests to verify email configuration is correct.

    These CAN be run automatically to check config.
    """

    def test_resend_configured_when_api_key_present(self):
        """Verify Resend is configured when API key is present."""
        try:
            email_host_password = settings.EMAIL_HOST_PASSWORD
        except AttributeError:
            email_host_password = None
        if email_host_password:
            if email_host_password.startswith("re_"):
                assert settings.EMAIL_HOST == "smtp.resend.com"
                assert settings.EMAIL_PORT == 587
                assert settings.EMAIL_USE_TLS
                assert settings.EMAIL_HOST_USER == "resend"

    def test_console_backend_fallback(self):
        """Verify console backend is used when no API key."""
        try:
            email_host_password = settings.EMAIL_HOST_PASSWORD
        except AttributeError:
            email_host_password = None
        if not email_host_password:
            assert settings.EMAIL_BACKEND == "django.core.mail.backends.console.EmailBackend"

    def test_email_verification_mandatory(self):
        """Verify email verification is set to mandatory."""
        assert settings.ACCOUNT_EMAIL_VERIFICATION == "mandatory"

    def test_frontend_urls_configured(self):
        """Verify frontend URLs are configured for email links."""
        assert "account_confirm_email" in settings.HEADLESS_FRONTEND_URLS
        confirm_url = settings.HEADLESS_FRONTEND_URLS["account_confirm_email"]
        assert "{key}" in confirm_url
        assert "verify-email" in confirm_url
