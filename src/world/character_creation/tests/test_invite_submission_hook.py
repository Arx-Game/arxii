"""Tests for invite annotation + notification on draft submission (#2483)."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.character_creation.factories import CharacterDraftFactory
from world.character_creation.services import submit_draft_for_review
from world.roster.factories import GameInviteFactory
from world.roster.models import InviteStatus


class InviteSubmissionHookTests(TestCase):
    """Tests that submit_draft_for_review annotates and notifies when an invite exists."""

    def test_submission_attaches_invite_when_present(self):
        """submit_draft_for_review sets invited_via when account has a claimed invite."""
        account = AccountFactory()
        invite = GameInviteFactory(
            status=InviteStatus.CLAIMED,
            invited_account=account,
        )
        draft = CharacterDraftFactory(account=account)
        draft.can_submit = lambda: True

        with patch(
            "world.roster.services.invite_notifications.notify_inviter_of_submission"
        ) as mock_notify:
            application = submit_draft_for_review(draft, submission_notes="")

        self.assertEqual(application.invited_via, invite)
        mock_notify.assert_called_once_with(invite, application)

    def test_submission_does_not_attach_when_no_invite(self):
        """submit_draft_for_review does not set invited_via when no invite."""
        account = AccountFactory()
        draft = CharacterDraftFactory(account=account)
        draft.can_submit = lambda: True

        with patch(
            "world.roster.services.invite_notifications.notify_inviter_of_submission"
        ) as mock_notify:
            application = submit_draft_for_review(draft, submission_notes="")

        self.assertIsNone(application.invited_via)
        mock_notify.assert_not_called()
