"""Tests for registration service functions: issue/revoke/redeem/signup_allowed."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import AccountFactory
from world.registration import services
from world.registration.factories import AccountInviteFactory
from world.registration.models import AccountInvite


class IssueInviteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(username="issue_invite_staff", is_staff=True)

    def test_issue_invite_creates_row(self):
        invite = services.issue_invite("New@Example.com", self.staff, note="alpha tester")
        self.assertEqual(invite.email, "new@example.com")
        self.assertEqual(invite.invited_by, self.staff)
        self.assertEqual(invite.note, "alpha tester")
        self.assertTrue(invite.token)
        self.assertTrue(invite.is_redeemable)

    def test_issue_invite_dedups_active_invite(self):
        first = services.issue_invite("dup@example.com", self.staff)
        second = services.issue_invite("dup@example.com", self.staff)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(AccountInvite.objects.filter(email="dup@example.com").count(), 1)

    def test_issue_invite_creates_fresh_row_when_only_dead_invites_exist(self):
        dead = AccountInviteFactory(
            invited_by=self.staff,
            email="dead@example.com",
            revoked_at=timezone.now(),
        )
        fresh = services.issue_invite("dead@example.com", self.staff)
        self.assertNotEqual(dead.pk, fresh.pk)
        self.assertTrue(fresh.is_redeemable)

    def test_issue_invite_creates_fresh_row_when_only_expired_invites_exist(self):
        AccountInviteFactory(
            invited_by=self.staff,
            email="stale@example.com",
            expires_at=timezone.now() - timedelta(days=1),
        )
        fresh = services.issue_invite("stale@example.com", self.staff)
        self.assertTrue(fresh.is_redeemable)
        self.assertEqual(AccountInvite.objects.filter(email="stale@example.com").count(), 2)


class RevokeInviteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(username="revoke_invite_staff", is_staff=True)

    def test_revoke_invite_stamps_revoked_at(self):
        invite = AccountInviteFactory(invited_by=self.staff)
        services.revoke_invite(invite, by=self.staff)
        invite.refresh_from_db()
        self.assertIsNotNone(invite.revoked_at)
        self.assertFalse(invite.is_redeemable)


class SignupAllowedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(username="signup_allowed_staff", is_staff=True)

    def test_valid_token_and_matching_email(self):
        invite = AccountInviteFactory(invited_by=self.staff, email="match@example.com")
        self.assertTrue(services.signup_allowed("match@example.com", invite.token))
        self.assertTrue(services.signup_allowed("MATCH@example.com", invite.token))

    def test_wrong_email_rejected(self):
        invite = AccountInviteFactory(invited_by=self.staff, email="match@example.com")
        self.assertFalse(services.signup_allowed("other@example.com", invite.token))

    def test_unknown_token_rejected(self):
        self.assertFalse(services.signup_allowed("match@example.com", "not-a-real-token"))

    def test_missing_email_or_token_rejected(self):
        self.assertFalse(services.signup_allowed("", "sometoken"))
        self.assertFalse(services.signup_allowed("match@example.com", ""))

    def test_revoked_invite_rejected(self):
        invite = AccountInviteFactory(
            invited_by=self.staff, email="match@example.com", revoked_at=timezone.now()
        )
        self.assertFalse(services.signup_allowed("match@example.com", invite.token))

    def test_expired_invite_rejected(self):
        invite = AccountInviteFactory(
            invited_by=self.staff,
            email="match@example.com",
            expires_at=timezone.now() - timedelta(days=1),
        )
        self.assertFalse(services.signup_allowed("match@example.com", invite.token))


class RedeemInviteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(username="redeem_invite_staff", is_staff=True)
        cls.invitee = AccountFactory(username="redeem_invite_invitee")

    def test_redeem_invite_stamps_redemption(self):
        invite = AccountInviteFactory(invited_by=self.staff, email="redeem@example.com")
        result = services.redeem_invite(invite.token, "redeem@example.com", self.invitee)
        self.assertIsNotNone(result)
        invite.refresh_from_db()
        self.assertIsNotNone(invite.redeemed_at)
        self.assertEqual(invite.redeemed_by, self.invitee)

    def test_redeem_invite_second_use_rejected(self):
        invite = AccountInviteFactory(invited_by=self.staff, email="redeem2@example.com")
        services.redeem_invite(invite.token, "redeem2@example.com", self.invitee)
        second_invitee = AccountFactory(username="redeem_invite_second_user")
        result = services.redeem_invite(invite.token, "redeem2@example.com", second_invitee)
        self.assertIsNone(result)

    def test_redeem_invite_wrong_email_rejected(self):
        invite = AccountInviteFactory(invited_by=self.staff, email="redeem3@example.com")
        result = services.redeem_invite(invite.token, "someone-else@example.com", self.invitee)
        self.assertIsNone(result)
        invite.refresh_from_db()
        self.assertIsNone(invite.redeemed_at)

    def test_redeem_invite_no_token_returns_none(self):
        self.assertIsNone(services.redeem_invite("", "redeem@example.com", self.invitee))

    def test_redeem_invite_unknown_token_returns_none(self):
        self.assertIsNone(
            services.redeem_invite("not-a-real-token", "redeem@example.com", self.invitee)
        )
