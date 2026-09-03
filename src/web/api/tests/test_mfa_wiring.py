"""allauth.mfa is installed with its optional dependency and its headless routes mount (#3591).

Installing ``allauth.mfa`` without the ``[mfa]`` extra crashes at import
(``allauth/mfa/stages.py`` -> ``webauthn/internal/flows.py`` -> ``import fido2``),
which would take the whole site down on the next converge, not just 2FA.
"""

import importlib

from django.conf import settings
from django.test import SimpleTestCase
from django.urls import reverse


class MfaWiringTests(SimpleTestCase):
    def test_mfa_app_installed(self):
        self.assertIn("allauth.mfa", settings.INSTALLED_APPS)

    def test_mfa_stages_import_without_webauthn(self):
        """The exact module that pulls fido2 in at load time."""
        importlib.import_module("allauth.mfa.stages")

    def test_headless_mfa_routes_mount(self):
        self.assertEqual(
            reverse("headless:browser:mfa:manage_totp"),
            "/api/auth/browser/v1/account/authenticators/totp",
        )
        self.assertEqual(
            reverse("headless:browser:mfa:manage_recovery_codes"),
            "/api/auth/browser/v1/account/authenticators/recovery-codes",
        )
        self.assertEqual(
            reverse("headless:browser:mfa:authenticate"),
            "/api/auth/browser/v1/auth/2fa/authenticate",
        )

    def test_settings_block(self):
        self.assertTrue(settings.ACCOUNT_CHANGE_EMAIL)
        self.assertTrue(settings.ACCOUNT_REAUTHENTICATION_REQUIRED)
        self.assertTrue(settings.ACCOUNT_EMAIL_NOTIFICATIONS)
        self.assertEqual(settings.MFA_SUPPORTED_TYPES, ["totp", "recovery_codes"])
        self.assertEqual(settings.MFA_TOTP_TOLERANCE, 1)
        self.assertTrue(settings.MFA_ALLOW_UNVERIFIED_EMAIL)
        self.assertEqual(settings.MFA_TOTP_ISSUER, "Arx II")
