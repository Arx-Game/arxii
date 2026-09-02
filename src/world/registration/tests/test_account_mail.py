"""allauth account mail names the game, not Django's ``sites`` placeholder.

allauth's stock ``account/email/*.txt`` templates read ``current_site`` off
Django's ``sites`` table, whose only row is the framework default
``example.com`` (nothing in this codebase ever set it), and with no
``ACCOUNT_EMAIL_SUBJECT_PREFIX`` the subject falls back to ``[example.com]``
the same way. A bare ``DEFAULT_FROM_EMAIL`` renders in Gmail as just its
mailbox ("noreply"). These tests pin the template overrides in
``src/web/templates/account/email/`` and the two settings that fix it.
"""

from email.utils import parseaddr

from allauth.core import context
from django.contrib.auth.models import AnonymousUser
from django.core import mail
from django.test import RequestFactory, TestCase

from evennia_extensions.adapters import ArxAccountAdapter
from evennia_extensions.factories import AccountFactory

ACTIVATE_URL = "https://play.arx2.com/verify-email/abc123"


class AccountMailTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory(username="mail_test_user", email="mail_test@test.invalid")

    def _send_confirmation(self) -> mail.EmailMessage:
        request = RequestFactory().get("/")
        request.user = AnonymousUser()  # Evennia's context processor reads it
        with context.request_context(request):
            ArxAccountAdapter().send_mail(
                "account/email/email_confirmation",
                self.account.email,
                {"user": self.account, "activate_url": ACTIVATE_URL, "key": "abc123"},
            )
        self.assertEqual(len(mail.outbox), 1)
        return mail.outbox[0]

    def test_confirmation_mail_names_the_game_not_the_sites_placeholder(self):
        message = self._send_confirmation()
        self.assertEqual(message.subject, "[Arx II] Please Confirm Your Email Address")
        self.assertNotIn("example.com", message.body)
        self.assertIn("Arx II", message.body)
        self.assertIn(ACTIVATE_URL, message.body)

    def test_from_address_carries_a_display_name(self):
        message = self._send_confirmation()
        name, address = parseaddr(message.from_email)
        self.assertEqual(name, "Arx II")
        self.assertIn("@", address)
