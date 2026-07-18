"""Tests for invite annotation on DraftApplication (#2483)."""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.character_creation.factories import DraftApplicationFactory
from world.roster.factories import GameInviteFactory
from world.roster.models import InviteStatus
from world.roster.services.invite_services import annotate_application


class AnnotateApplicationTests(TestCase):
    def test_attaches_invite_when_account_has_claimed_invite(self):
        """annotate_application sets invited_via when the account has a claimed invite."""
        account = AccountFactory()
        invite = GameInviteFactory(
            status=InviteStatus.CLAIMED,
            invited_account=account,
        )
        application = DraftApplicationFactory(player_account=account)
        result = annotate_application(application, account)
        self.assertEqual(result, invite)
        application.refresh_from_db()
        self.assertEqual(application.invited_via, invite)

    def test_returns_none_when_account_has_no_invite(self):
        """annotate_application returns None and does not set invited_via when no invite."""
        account = AccountFactory()
        application = DraftApplicationFactory(player_account=account)
        result = annotate_application(application, account)
        self.assertIsNone(result)
        application.refresh_from_db()
        self.assertIsNone(application.invited_via)
