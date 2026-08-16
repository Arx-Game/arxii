"""Tests for invite email delivery.

Before this existed, issuing an invite wrote a row and nothing else: the only
delivery path was the staff page's Copy Link button, even though Resend was
already wired up as the SMTP backend. These tests pin the behaviour that
closed that gap.
"""

from unittest.mock import patch

from django.core import mail
from django.template import TemplateDoesNotExist
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.registration import services
from world.registration.email_service import build_invite_url
from world.registration.factories import AccountInviteFactory

SITE = "https://arx2.example"


@override_settings(SITE_URL=SITE)
class InviteEmailSendTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(username="invite_mail_staff", is_staff=True)

    def test_issuing_an_invite_emails_the_invitee(self):
        invite = services.issue_invite("newcomer@example.com", self.staff)

        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertEqual(sent.to, ["newcomer@example.com"])
        self.assertIn(build_invite_url(invite.token), sent.body)

    def test_email_carries_the_redemption_link_for_this_token(self):
        invite = services.issue_invite("linked@example.com", self.staff)

        expected = f"{SITE}/register?invite={invite.token}"
        self.assertEqual(build_invite_url(invite.token), expected)
        self.assertIn(expected, mail.outbox[0].body)

    def test_reissuing_for_an_active_invite_sends_again_without_duplicating(self):
        first = services.issue_invite("again@example.com", self.staff)
        mail.outbox.clear()

        second = services.issue_invite("again@example.com", self.staff)

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(build_invite_url(first.token), mail.outbox[0].body)

    def test_a_bounced_send_never_undoes_the_invite(self):
        """A dead SMTP relay must leave a usable invite behind for Copy Link."""
        target = "world.registration.email_service.RegistrationEmailService._send_email"
        with patch(target, return_value=False) as send:
            invite = services.issue_invite("bounced@example.com", self.staff)

        send.assert_called_once()
        self.assertTrue(invite.is_redeemable)
        self.assertTrue(invite.token)

    def test_a_broken_template_never_undoes_the_invite(self):
        """A missing template is a deploy fault; the invite must still stand."""
        target = "world.registration.email_service.render_to_string"
        with (
            self.assertLogs("world.registration.email_service", level="ERROR"),
            patch(target, side_effect=TemplateDoesNotExist("account_invite.html")),
        ):
            invite = services.issue_invite("noTemplate@example.com", self.staff)

        self.assertEqual(len(mail.outbox), 0)
        self.assertTrue(invite.is_redeemable)


@override_settings(SITE_URL=SITE)
class InviteResendEndpointTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(username="invite_resend_staff", is_staff=True)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.staff)
        self.list_url = "/api/staff/invites/"

    def test_resend_mails_a_pending_invite_again(self):
        invite = AccountInviteFactory(invited_by=self.staff, email="resend@example.com")
        mail.outbox.clear()

        response = self.client.post(f"{self.list_url}{invite.pk}/resend/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["resend@example.com"])
        self.assertIn(build_invite_url(invite.token), mail.outbox[0].body)

    def test_resend_refuses_a_revoked_invite(self):
        invite = AccountInviteFactory(invited_by=self.staff, email="revoked@example.com")
        invite.revoked_at = timezone.now()
        invite.save(update_fields=["revoked_at"])
        mail.outbox.clear()

        response = self.client.post(f"{self.list_url}{invite.pk}/resend/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["status"], "revoked")
        self.assertEqual(len(mail.outbox), 0)

    def test_resend_refuses_a_redeemed_invite(self):
        invite = AccountInviteFactory(invited_by=self.staff, email="used@example.com")
        invite.redeemed_at = timezone.now()
        invite.save(update_fields=["redeemed_at"])
        mail.outbox.clear()

        response = self.client.post(f"{self.list_url}{invite.pk}/resend/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(len(mail.outbox), 0)

    def test_resend_is_staff_only(self):
        invite = AccountInviteFactory(invited_by=self.staff, email="guarded@example.com")
        player = AccountFactory(username="invite_resend_player", is_staff=False)
        self.client.force_authenticate(player)
        mail.outbox.clear()

        response = self.client.post(f"{self.list_url}{invite.pk}/resend/")

        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )
        self.assertEqual(len(mail.outbox), 0)
