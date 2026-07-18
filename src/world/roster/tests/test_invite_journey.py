"""End-to-end journey test for the game invite flow (#2483).

Exercises: create invite → resolve → claim → submit draft → annotation + notification.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.character_creation.factories import CharacterDraftFactory
from world.character_creation.services import submit_draft_for_review
from world.roster.factories import PlayerDataFactory
from world.roster.models import InviteStatus
from world.roster.services.invite_services import (
    claim_game_invite,
    create_game_invite,
    resolve_invite,
)
from world.stories.factories import PlayerTrustFactory, TrustCategoryFactory
from world.stories.models import PlayerTrustLevel
from world.stories.types import TrustLevel


class InvitedPlayerFullJourneyTests(TestCase):
    def test_full_invite_journey(self):
        """Full flow: inviter creates invite → friend claims → submits → inviter notified."""
        # 1. Inviter creates invite
        inviter_pd = PlayerDataFactory()
        invite_category = TrustCategoryFactory(name="INVITE")
        trust = PlayerTrustFactory(account=inviter_pd.account)
        PlayerTrustLevel.objects.create(
            player_trust=trust,
            trust_category=invite_category,
            trust_level=TrustLevel.BASIC,
        )
        invite = create_game_invite(
            inviter=inviter_pd,
            message="We need a healer for our group!",
        )
        self.assertEqual(invite.status, InviteStatus.PENDING)
        self.assertTrue(invite.token)

        # 2. Resolve (registration page context display)
        resolved = resolve_invite(invite.token)
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.message, "We need a healer for our group!")

        # 3. Friend registers and claims invite on first login
        friend_account = AccountFactory()
        claimed = claim_game_invite(invite.token, friend_account)
        self.assertEqual(claimed.status, InviteStatus.CLAIMED)
        self.assertEqual(claimed.invited_account, friend_account)

        # 4. Friend completes CG and submits
        draft = CharacterDraftFactory(account=friend_account)
        draft.can_submit = lambda: True

        with patch(
            "world.roster.services.invite_notifications.notify_inviter_of_submission"
        ) as mock_notify:
            application = submit_draft_for_review(draft, submission_notes="Excited to play!")

        # 5. Application is annotated with invite context
        self.assertEqual(application.invited_via, invite)

        # 6. Inviter was notified
        mock_notify.assert_called_once_with(invite, application)
