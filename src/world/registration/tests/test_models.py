"""Tests for registration models: singleton accessor + derived invite status."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import AccountFactory
from world.registration.constants import InviteStatus
from world.registration.factories import AccountInviteFactory
from world.registration.models import RegistrationConfig, get_registration_config


class RegistrationConfigTests(TestCase):
    def test_get_registration_config_creates_closed_singleton(self):
        self.assertEqual(RegistrationConfig.objects.count(), 0)
        config = get_registration_config()
        self.assertEqual(config.pk, 1)
        self.assertFalse(config.registration_open)
        self.assertEqual(RegistrationConfig.objects.count(), 1)

    def test_get_registration_config_returns_existing_singleton(self):
        first = get_registration_config()
        first.registration_open = True
        first.save(update_fields=["registration_open"])

        second = get_registration_config()
        self.assertEqual(second.pk, first.pk)
        self.assertTrue(second.registration_open)


class AccountInviteStatusTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(username="invite_status_staff", is_staff=True)

    def test_status_pending_by_default(self):
        invite = AccountInviteFactory(invited_by=self.staff)
        self.assertEqual(invite.status, InviteStatus.PENDING)
        self.assertTrue(invite.is_redeemable)

    def test_status_redeemed(self):
        invitee = AccountFactory(username="invite_status_redeemed_user")
        invite = AccountInviteFactory(
            invited_by=self.staff,
            redeemed_at=timezone.now(),
            redeemed_by=invitee,
        )
        self.assertEqual(invite.status, InviteStatus.REDEEMED)
        self.assertFalse(invite.is_redeemable)

    def test_status_revoked(self):
        invite = AccountInviteFactory(invited_by=self.staff, revoked_at=timezone.now())
        self.assertEqual(invite.status, InviteStatus.REVOKED)
        self.assertFalse(invite.is_redeemable)

    def test_status_expired(self):
        invite = AccountInviteFactory(
            invited_by=self.staff, expires_at=timezone.now() - timedelta(days=1)
        )
        self.assertEqual(invite.status, InviteStatus.EXPIRED)
        self.assertFalse(invite.is_redeemable)

    def test_revoked_takes_precedence_over_redeemed(self):
        """A revoked-after-redeemed invite (shouldn't normally happen) still reports revoked."""
        invitee = AccountFactory(username="invite_status_both_user")
        invite = AccountInviteFactory(
            invited_by=self.staff,
            redeemed_at=timezone.now(),
            redeemed_by=invitee,
            revoked_at=timezone.now(),
        )
        self.assertEqual(invite.status, InviteStatus.REVOKED)
