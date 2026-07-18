"""Tests for GameInviteViewSet API endpoints (#2483)."""

from __future__ import annotations

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.roster.factories import GameInviteFactory, PlayerDataFactory
from world.roster.models import InviteStatus
from world.stories.factories import PlayerTrustFactory, TrustCategoryFactory
from world.stories.models import PlayerTrustLevel
from world.stories.types import TrustLevel


class GameInviteAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.account = AccountFactory()
        self.player_data = PlayerDataFactory(account=self.account)
        self.invite_category = TrustCategoryFactory(name="INVITE")
        trust = PlayerTrustFactory(account=self.account)
        PlayerTrustLevel.objects.create(
            player_trust=trust,
            trust_category=self.invite_category,
            trust_level=TrustLevel.BASIC,
        )
        self.client.force_authenticate(user=self.account)

    def test_create_invite(self):
        """POST /api/roster/invites/ creates an invite."""
        url = reverse("roster:gameinvite-list")
        response = self.client.post(url, {"message": "Come play Arx!"}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertIn("token", response.data)
        self.assertIn("message", response.data)

    def test_list_own_invites(self):
        """GET /api/roster/invites/ returns only the inviter's own invites."""
        invite = GameInviteFactory(inviter=self.player_data)
        GameInviteFactory()  # Another player's invite
        url = reverse("roster:gameinvite-list")
        response = self.client.get(url, format="json")
        self.assertEqual(response.status_code, 200)
        # Results may be paginated or a plain list
        results = response.data.get("results", response.data)
        invite_ids = [item["id"] for item in results]
        self.assertIn(invite.id, invite_ids)

    def test_revoke_own_invite(self):
        """POST /api/roster/invites/{id}/revoke/ revokes own invite."""
        invite = GameInviteFactory(inviter=self.player_data)
        url = reverse("roster:gameinvite-revoke", kwargs={"pk": invite.pk})
        response = self.client.post(url, format="json")
        self.assertEqual(response.status_code, 200)
        invite.refresh_from_db()
        self.assertEqual(invite.status, InviteStatus.REVOKED)

    def test_claim_invite(self):
        """POST /api/roster/invites/claim/ claims a token."""
        invite = GameInviteFactory(status=InviteStatus.PENDING)
        # Claim as a different account
        other_account = AccountFactory()
        self.client.force_authenticate(user=other_account)
        url = reverse("roster:gameinvite-claim")
        response = self.client.post(url, {"token": invite.token}, format="json")
        self.assertEqual(response.status_code, 200)
        invite.refresh_from_db()
        self.assertEqual(invite.status, InviteStatus.CLAIMED)
        self.assertEqual(invite.invited_account, other_account)

    def test_resolve_invite_allowany(self):
        """GET /api/roster/invites/resolve/?token=TOKEN works without auth."""
        invite = GameInviteFactory(status=InviteStatus.PENDING)
        self.client.force_authenticate(user=None)
        url = reverse("roster:gameinvite-resolve")
        response = self.client.get(url, {"token": invite.token}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("message", response.data)

    def test_resolve_invite_returns_404_for_nonexistent(self):
        """GET /api/roster/invites/resolve/?token=BAD returns 404."""
        self.client.force_authenticate(user=None)
        url = reverse("roster:gameinvite-resolve")
        response = self.client.get(url, {"token": "nonexistent"}, format="json")
        self.assertEqual(response.status_code, 404)
