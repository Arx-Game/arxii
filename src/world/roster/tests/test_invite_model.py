"""Tests for the GameInvite model."""

from __future__ import annotations

from django.test import TestCase

from world.roster.factories import PlayerDataFactory
from world.roster.models import GameInvite, InviteStatus


class GameInviteModelTests(TestCase):
    def test_create_invite_defaults_to_pending(self):
        """A new GameInvite defaults to PENDING status."""
        player_data = PlayerDataFactory()
        invite = GameInvite.objects.create(
            inviter=player_data,
            token="test-token-123",
            message="Come play Arx!",
        )
        self.assertEqual(invite.status, InviteStatus.PENDING)
        self.assertIsNone(invite.claimed_at)
        self.assertIsNone(invite.invited_account)

    def test_is_usable_true_for_pending(self):
        """A pending invite is usable."""
        player_data = PlayerDataFactory()
        invite = GameInvite.objects.create(
            inviter=player_data,
            token="test-token-456",
            message="Come play!",
        )
        self.assertTrue(invite.is_usable)

    def test_is_usable_false_after_claimed(self):
        """A claimed invite is not usable."""
        player_data = PlayerDataFactory()
        invite = GameInvite.objects.create(
            inviter=player_data,
            token="test-token-789",
            message="Come play!",
            status=InviteStatus.CLAIMED,
        )
        self.assertFalse(invite.is_usable)

    def test_is_usable_false_after_revoked(self):
        """A revoked invite is not usable."""
        player_data = PlayerDataFactory()
        invite = GameInvite.objects.create(
            inviter=player_data,
            token="test-token-revoked",
            message="Come play!",
            status=InviteStatus.REVOKED,
        )
        self.assertFalse(invite.is_usable)

    def test_str_representation(self):
        """__str__ includes token prefix and status."""
        player_data = PlayerDataFactory()
        invite = GameInvite.objects.create(
            inviter=player_data,
            token="abcdef1234567890",
            message="Come play!",
        )
        self.assertIn("abcdef12", str(invite))
        self.assertIn("pending", str(invite).lower())
