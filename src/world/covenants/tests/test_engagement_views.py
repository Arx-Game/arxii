"""View action tests for the engagement endpoints (Tasks 7.5 + 7.6).

Uses setUp (not setUpTestData) — see pre-existing deepcopy issue with Evennia
DbHolder when SharedMemoryModel instances are stored on the class during
setUpTestData.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.constants import CovenantType
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
# IsOwnMembership authorization tests
# ---------------------------------------------------------------------------


class EngagementViewAuthorizationTests(TestCase):
    """IsOwnMembership permission tests for the engage endpoint."""

    def setUp(self) -> None:
        self.owner = _make_user("eng_auth_owner")
        self.other = _make_user("eng_auth_other")
        self.sheet = _setup_user_with_sheet(self.owner)
        self.other_sheet = _setup_user_with_sheet(self.other)

        role = CovenantRoleFactory(covenant_type=CovenantType.BATTLE)
        cov = CovenantFactory(covenant_type=CovenantType.BATTLE)
        self.membership = CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant=cov,
            covenant_role=role,
        )

        self.owner_client = APIClient()
        self.owner_client.force_authenticate(user=self.owner)

        self.other_client = APIClient()
        self.other_client.force_authenticate(user=self.other)

    def test_engage_denies_non_owner(self) -> None:
        """404 when the requesting user doesn't play this membership's sheet.

        The list-view queryset scoping (active RosterTenure chain) excludes
        memberships the user doesn't own, so DRF returns 404 from get_object()
        before the IsOwnMembership permission class is even consulted.
        """
        response = self.other_client.post(
            f"/api/covenants/character-roles/{self.membership.pk}/engage/"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_engage_allows_owner(self) -> None:
        """200 when the requesting user owns the sheet.

        The BATTLE covenant here is risen (not dormant), so can_engage_membership
        returns True and the request reaches the success path. (A dormant battle
        covenant would be blocked — see test_battle_engagement.)
        """
        response = self.owner_client.post(
            f"/api/covenants/character-roles/{self.membership.pk}/engage/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["engaged"])

    def test_engage_allows_staff(self) -> None:
        """Staff bypass the ownership predicate."""
        staff = _make_user("eng_auth_staff", is_staff=True)
        staff_client = APIClient()
        staff_client.force_authenticate(user=staff)
        response = staff_client.post(f"/api/covenants/character-roles/{self.membership.pk}/engage/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_disengage_denies_non_owner(self) -> None:
        """404 for disengage when user doesn't own the sheet.

        Same queryset scoping as engage — non-owner never sees the object.
        """
        response = self.other_client.post(
            f"/api/covenants/character-roles/{self.membership.pk}/disengage/"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


# ---------------------------------------------------------------------------
# Engage prerequisite tests (DURANCE covenant — has IC gate)
# ---------------------------------------------------------------------------


class EngagePrerequisiteTests(TestCase):
    """Test the IC prerequisite gate on the engage endpoint."""

    def setUp(self) -> None:
        self.user = _make_user("eng_prereq_user")
        self.sheet = _setup_user_with_sheet(self.user)

        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        cov = CovenantFactory(covenant_type=CovenantType.DURANCE)
        self.membership = CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant=cov,
            covenant_role=role,
        )

        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_engage_returns_400_when_prerequisite_not_met(self) -> None:
        """can_engage_membership returning False → 400 with user_message."""
        with patch(
            "world.covenants.views.can_engage_membership",
            return_value=False,
        ):
            response = self.client.post(
                f"/api/covenants/character-roles/{self.membership.pk}/engage/"
            )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", response.data)
        self.assertEqual(
            response.data["detail"],
            "No covenant members present to engage with.",
        )

    def test_engage_returns_200_and_engaged_when_prerequisite_met(self) -> None:
        """Sets engaged=True when prerequisite passes."""
        with patch(
            "world.covenants.views.can_engage_membership",
            return_value=True,
        ):
            response = self.client.post(
                f"/api/covenants/character-roles/{self.membership.pk}/engage/"
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["engaged"])
        self.membership.refresh_from_db()
        self.assertTrue(self.membership.engaged)


# ---------------------------------------------------------------------------
# Disengage action tests
# ---------------------------------------------------------------------------


class DisengageActionTests(TestCase):
    """Test the disengage action endpoint."""

    def setUp(self) -> None:
        self.user = _make_user("eng_disengage_user")
        self.sheet = _setup_user_with_sheet(self.user)

        role = CovenantRoleFactory(covenant_type=CovenantType.BATTLE)
        cov = CovenantFactory(covenant_type=CovenantType.BATTLE)
        self.membership = CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant=cov,
            covenant_role=role,
            engaged=True,
        )

        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_disengage_clears_engagement(self) -> None:
        """Disengaging an engaged membership sets engaged=False."""
        response = self.client.post(
            f"/api/covenants/character-roles/{self.membership.pk}/disengage/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["engaged"])
        self.membership.refresh_from_db()
        self.assertFalse(self.membership.engaged)

    def test_disengage_is_idempotent(self) -> None:
        """Disengaging an already-disengaged membership returns 200, not error."""
        self.membership.engaged = False
        self.membership.save(update_fields=["engaged"])
        response = self.client.post(
            f"/api/covenants/character-roles/{self.membership.pk}/disengage/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["engaged"])


# ---------------------------------------------------------------------------
# Serializer field tests
# ---------------------------------------------------------------------------


class CanEngageSerializerFieldTests(TestCase):
    """Test the can_engage + engage_blocked_reason serializer fields."""

    def setUp(self) -> None:
        self.user = _make_user("eng_serial_user")
        self.sheet = _setup_user_with_sheet(self.user)

        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        cov = CovenantFactory(covenant_type=CovenantType.DURANCE)
        self.membership = CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant=cov,
            covenant_role=role,
        )

        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_can_engage_true_when_prerequisite_met(self) -> None:
        """can_engage field is True when IC prerequisite passes."""
        with patch(
            "world.covenants.serializers.can_engage_membership",
            return_value=True,
        ):
            response = self.client.get(f"/api/covenants/character-roles/{self.membership.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["can_engage"])
        self.assertIsNone(response.data["engage_blocked_reason"])

    def test_can_engage_false_with_blocked_reason(self) -> None:
        """can_engage is False and engage_blocked_reason is set when prerequisite fails."""
        with patch(
            "world.covenants.serializers.can_engage_membership",
            return_value=False,
        ):
            response = self.client.get(f"/api/covenants/character-roles/{self.membership.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["can_engage"])
        self.assertEqual(
            response.data["engage_blocked_reason"],
            "No covenant members present in this scene.",
        )
