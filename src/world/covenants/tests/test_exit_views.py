"""View action tests for the covenant exit endpoints (leave + kick, #519).

Uses setUp (not setUpTestData) — see the pre-existing deepcopy issue with
Evennia DbHolder when SharedMemoryModel instances are stored on the class during
setUpTestData (mirrors test_engagement_views.py).
"""

from __future__ import annotations

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.constants import CovenantType
from world.covenants.exceptions import CannotKickLeaderError
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
)
from world.roster.factories import (
    PlayerDataFactory,
    RosterEntryFactory,
    RosterTenureFactory,
)


def _make_user(username: str, *, is_staff: bool = False) -> object:
    from evennia.accounts.models import AccountDB

    return AccountDB.objects.create_user(
        username=username,
        email=f"{username}@test.com",
        password="testpass",
        is_staff=is_staff,
    )


def _setup_user_with_sheet(user: object) -> object:
    """Create a CharacterSheet with an active RosterTenure for *user*.

    Returns the CharacterSheet.
    """
    sheet = CharacterSheetFactory()
    entry = RosterEntryFactory(character_sheet=sheet)
    player_data = PlayerDataFactory(account=user)
    RosterTenureFactory(roster_entry=entry, player_data=player_data, end_date=None)
    return sheet


# ---------------------------------------------------------------------------
# leave action
# ---------------------------------------------------------------------------


class LeaveActionTests(TestCase):
    """Tests for the /character-roles/{id}/leave/ self-leave action."""

    def setUp(self) -> None:
        self.owner = _make_user("exit_leave_owner")
        self.other = _make_user("exit_leave_other")
        self.sheet = _setup_user_with_sheet(self.owner)
        self.other_sheet = _setup_user_with_sheet(self.other)

        # Three-member covenant so a single leave does not auto-dissolve it,
        # keeping the soft-end visible without dissolution side effects.
        self.cov = CovenantFactory(covenant_type=CovenantType.DURANCE)
        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        self.membership = CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant=self.cov,
            covenant_role=role,
        )
        CharacterCovenantRoleFactory(
            character_sheet=self.other_sheet,
            covenant=self.cov,
            covenant_role=role,
        )
        CharacterCovenantRoleFactory(
            character_sheet=CharacterSheetFactory(),
            covenant=self.cov,
            covenant_role=role,
        )

        self.owner_client = APIClient()
        self.owner_client.force_authenticate(user=self.owner)
        self.other_client = APIClient()
        self.other_client.force_authenticate(user=self.other)

    def test_leave_self_soft_ends_membership(self) -> None:
        """Leaving one's own membership returns 200 and soft-ends the row."""
        response = self.owner_client.post(
            f"/api/covenants/character-roles/{self.membership.pk}/leave/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["is_active"])
        self.assertIsNotNone(response.data["left_at"])
        self.membership.refresh_from_db()
        self.assertIsNotNone(self.membership.left_at)

    def test_leave_someone_elses_membership_denied(self) -> None:
        """A user cannot leave a membership they do not play.

        The membership-scoped get_queryset hides it, so get_object() 404s before
        IsOwnMembership is consulted.
        """
        response = self.other_client.post(
            f"/api/covenants/character-roles/{self.membership.pk}/leave/"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.membership.refresh_from_db()
        self.assertIsNone(self.membership.left_at)


# ---------------------------------------------------------------------------
# kick action
# ---------------------------------------------------------------------------


class KickActionTests(TestCase):
    """Tests for the /character-roles/{id}/kick/ leader-removes-member action."""

    def setUp(self) -> None:
        self.leader_user = _make_user("exit_kick_leader")
        self.target_user = _make_user("exit_kick_target")
        self.nonleader_user = _make_user("exit_kick_nonleader")

        self.leader_sheet = _setup_user_with_sheet(self.leader_user)
        self.target_sheet = _setup_user_with_sheet(self.target_user)
        self.nonleader_sheet = _setup_user_with_sheet(self.nonleader_user)

        self.cov = CovenantFactory(covenant_type=CovenantType.DURANCE)
        self.leader_role = CovenantRoleFactory(
            covenant_type=CovenantType.DURANCE,
            is_leadership=True,
        )
        self.member_role = CovenantRoleFactory(
            covenant_type=CovenantType.DURANCE,
            is_leadership=False,
        )

        self.leader_membership = CharacterCovenantRoleFactory(
            character_sheet=self.leader_sheet,
            covenant=self.cov,
            covenant_role=self.leader_role,
        )
        self.target_membership = CharacterCovenantRoleFactory(
            character_sheet=self.target_sheet,
            covenant=self.cov,
            covenant_role=self.member_role,
        )
        self.nonleader_membership = CharacterCovenantRoleFactory(
            character_sheet=self.nonleader_sheet,
            covenant=self.cov,
            covenant_role=self.member_role,
        )

        self.leader_client = APIClient()
        self.leader_client.force_authenticate(user=self.leader_user)
        self.target_client = APIClient()
        self.target_client.force_authenticate(user=self.target_user)
        self.nonleader_client = APIClient()
        self.nonleader_client.force_authenticate(user=self.nonleader_user)

    def test_leader_kicks_nonleader_soft_ends_target(self) -> None:
        """A leader removing a non-leader returns 200 and soft-ends the target."""
        response = self.leader_client.post(
            f"/api/covenants/character-roles/{self.target_membership.pk}/kick/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["is_active"])
        self.target_membership.refresh_from_db()
        self.assertIsNotNone(self.target_membership.left_at)

    def test_nonleader_cannot_kick(self) -> None:
        """A non-leader requester is denied (403) and the target is untouched."""
        response = self.nonleader_client.post(
            f"/api/covenants/character-roles/{self.target_membership.pk}/kick/"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.target_membership.refresh_from_db()
        self.assertIsNone(self.target_membership.left_at)

    def test_leader_cannot_kick_fellow_leader(self) -> None:
        """Kicking another leader returns 400 with CannotKickLeaderError's message."""
        second_leader_user = _make_user("exit_kick_leader2")
        second_leader_sheet = _setup_user_with_sheet(second_leader_user)
        second_leader_membership = CharacterCovenantRoleFactory(
            character_sheet=second_leader_sheet,
            covenant=self.cov,
            covenant_role=self.leader_role,
        )
        response = self.leader_client.post(
            f"/api/covenants/character-roles/{second_leader_membership.pk}/kick/"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], CannotKickLeaderError.user_message)
        second_leader_membership.refresh_from_db()
        self.assertIsNone(second_leader_membership.left_at)

    def test_kick_nonexistent_target_404(self) -> None:
        """Kicking a nonexistent pk returns 404 (get_object_or_404)."""
        response = self.leader_client.post("/api/covenants/character-roles/999999/kick/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
