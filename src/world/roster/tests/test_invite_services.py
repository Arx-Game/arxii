"""Tests for game invite services (#2483)."""

from __future__ import annotations

from django.test import TestCase

from world.roster.factories import GameInviteFactory, PlayerDataFactory
from world.roster.models import InviteStatus
from world.roster.services.invite_services import (
    claim_game_invite,
    create_game_invite,
    get_invite_for_account,
    resolve_invite,
    revoke_game_invite,
)
from world.stories.factories import PlayerTrustFactory, TrustCategoryFactory
from world.stories.models import PlayerTrustLevel
from world.stories.types import TrustLevel


class CreateGameInviteTests(TestCase):
    def setUp(self):
        self.invite_category = TrustCategoryFactory(name="INVITE")

    def test_creates_invite_with_token_and_pending_status(self):
        """create_game_invite generates a token and sets PENDING status."""
        player_data = PlayerDataFactory()
        trust = PlayerTrustFactory(account=player_data.account)
        PlayerTrustLevel.objects.create(
            player_trust=trust,
            trust_category=self.invite_category,
            trust_level=TrustLevel.BASIC,
        )
        invite = create_game_invite(
            inviter=player_data,
            message="We need a healer!",
        )
        self.assertEqual(invite.status, InviteStatus.PENDING)
        self.assertTrue(invite.token)
        self.assertEqual(invite.message, "We need a healer!")
        self.assertEqual(invite.inviter, player_data)

    def test_rejects_inviter_without_trust_profile(self):
        """create_game_invite raises if inviter has no trust profile."""
        player_data = PlayerDataFactory()
        # No PlayerTrust created → UNTRUSTED
        with self.assertRaises(PermissionError):
            create_game_invite(
                inviter=player_data,
                message="Come play!",
            )

    def test_rejects_inviter_below_trust_threshold(self):
        """create_game_invite raises if inviter has UNTRUSTED level."""
        player_data = PlayerDataFactory()
        trust = PlayerTrustFactory(account=player_data.account)
        PlayerTrustLevel.objects.create(
            player_trust=trust,
            trust_category=self.invite_category,
            trust_level=TrustLevel.UNTRUSTED,
        )
        with self.assertRaises(PermissionError):
            create_game_invite(
                inviter=player_data,
                message="Come play!",
            )

    def test_sets_expiry_when_expires_in_days_provided(self):
        """create_game_invite sets expires_at when expires_in_days is given."""
        player_data = PlayerDataFactory()
        trust = PlayerTrustFactory(account=player_data.account)
        PlayerTrustLevel.objects.create(
            player_trust=trust,
            trust_category=self.invite_category,
            trust_level=TrustLevel.BASIC,
        )
        invite = create_game_invite(
            inviter=player_data,
            message="Come play!",
            expires_in_days=7,
        )
        self.assertIsNotNone(invite.expires_at)

    def test_no_expiry_by_default(self):
        """create_game_invite sets expires_at to None by default."""
        player_data = PlayerDataFactory()
        trust = PlayerTrustFactory(account=player_data.account)
        PlayerTrustLevel.objects.create(
            player_trust=trust,
            trust_category=self.invite_category,
            trust_level=TrustLevel.BASIC,
        )
        invite = create_game_invite(
            inviter=player_data,
            message="Come play!",
        )
        self.assertIsNone(invite.expires_at)


class ResolveInviteTests(TestCase):
    def test_resolves_pending_invite(self):
        """resolve_invite returns a pending invite by token."""
        invite = GameInviteFactory(status=InviteStatus.PENDING)
        result = resolve_invite(invite.token)
        self.assertEqual(result, invite)

    def test_returns_none_for_claimed_invite(self):
        """resolve_invite returns None for a claimed invite."""
        invite = GameInviteFactory(status=InviteStatus.CLAIMED)
        self.assertIsNone(resolve_invite(invite.token))

    def test_returns_none_for_revoked_invite(self):
        """resolve_invite returns None for a revoked invite."""
        invite = GameInviteFactory(status=InviteStatus.REVOKED)
        self.assertIsNone(resolve_invite(invite.token))

    def test_returns_none_for_nonexistent_token(self):
        """resolve_invite returns None for a nonexistent token."""
        self.assertIsNone(resolve_invite("nonexistent-token"))


class ClaimGameInviteTests(TestCase):
    def test_claims_pending_invite(self):
        """claim_game_invite links account and sets CLAIMED status."""
        from evennia_extensions.factories import AccountFactory

        invite = GameInviteFactory(status=InviteStatus.PENDING)
        account = AccountFactory()
        claimed = claim_game_invite(invite.token, account)
        self.assertEqual(claimed.status, InviteStatus.CLAIMED)
        self.assertEqual(claimed.invited_account, account)
        self.assertIsNotNone(claimed.claimed_at)

    def test_rejects_already_claimed(self):
        """claim_game_invite raises for an already-claimed invite."""
        from evennia_extensions.factories import AccountFactory

        invite = GameInviteFactory(status=InviteStatus.CLAIMED)
        with self.assertRaises(ValueError):
            claim_game_invite(invite.token, AccountFactory())

    def test_rejects_revoked(self):
        """claim_game_invite raises for a revoked invite."""
        from evennia_extensions.factories import AccountFactory

        invite = GameInviteFactory(status=InviteStatus.REVOKED)
        with self.assertRaises(ValueError):
            claim_game_invite(invite.token, AccountFactory())


class RevokeGameInviteTests(TestCase):
    def test_revokes_pending_invite(self):
        """revoke_game_invite sets REVOKED status."""
        from evennia_extensions.factories import AccountFactory

        invite = GameInviteFactory(status=InviteStatus.PENDING)
        account = AccountFactory()
        revoke_game_invite(invite, revoked_by=account)
        invite.refresh_from_db()
        self.assertEqual(invite.status, InviteStatus.REVOKED)
        self.assertIsNotNone(invite.revoked_at)
        self.assertEqual(invite.revoked_by, account)


class GetInviteForAccountTests(TestCase):
    def test_returns_claimed_invite_for_account(self):
        """get_invite_for_account returns the claimed invite."""
        from evennia_extensions.factories import AccountFactory

        account = AccountFactory()
        invite = GameInviteFactory(
            status=InviteStatus.CLAIMED,
            invited_account=account,
        )
        result = get_invite_for_account(account)
        self.assertEqual(result, invite)

    def test_returns_none_for_account_without_invite(self):
        """get_invite_for_account returns None for uninvited account."""
        from evennia_extensions.factories import AccountFactory

        account = AccountFactory()
        self.assertIsNone(get_invite_for_account(account))
