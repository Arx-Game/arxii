"""Tests for ThreadViewSet.cross_xp_lock action (Spec A §3.2).

POST /api/magic/threads/{id}/cross-xp-lock/

Covers:
- Happy path: owner with sufficient XP unlocks a boundary
- XPInsufficient: 400 with typed user_message
- AnchorCapExceeded: boundary above effective cap → 400
- InvalidImbueAmount: boundary at/below thread.level → 400
- Permission: non-owner gets 404 (queryset ownership filter)
- Idempotency: repeat call returns same unlock_id without re-spending
"""

from __future__ import annotations

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import (
    ResonanceFactory,
    ThreadFactory,
    ThreadLevelUnlockFactory,
    ThreadXPLockedLevelFactory,
)
from world.magic.models import ThreadLevelUnlock
from world.progression.models import ExperiencePointsData
from world.roster.factories import RosterTenureFactory


def _link_account_to_sheet(account, character, sheet):
    """Tie an AccountDB to a CharacterSheet via an active RosterTenure.

    Also sets character.account so that service functions that navigate
    character_sheet.character.account resolve correctly.
    """
    character.account = account
    account.characters.add(character)
    return RosterTenureFactory(
        roster_entry__character_sheet=sheet,
        player_data__account=account,
    )


def _give_xp(account, amount: int) -> ExperiencePointsData:
    """Create or update an ExperiencePointsData row so current_available == amount."""
    xp, _ = ExperiencePointsData.objects.get_or_create(
        account=account,
        defaults={"total_earned": amount, "total_spent": 0},
    )
    if xp.current_available != amount:
        xp.total_earned = xp.total_spent + amount
        xp.save(update_fields=["total_earned"])
    return xp


class CrossXPLockViewTests(APITestCase):
    """Tests for ThreadViewSet.cross_xp_lock action."""

    @classmethod
    def setUpTestData(cls) -> None:
        # Owner account / character / sheet
        cls.account = AccountFactory(username="xp_lock_owner")
        cls.character = CharacterFactory(db_key="XPLockOwner")
        cls.sheet = CharacterSheetFactory(character=cls.character)
        _link_account_to_sheet(cls.account, cls.character, cls.sheet)

        # Non-owner
        cls.other_account = AccountFactory(username="xp_lock_other")
        cls.other_character = CharacterFactory(db_key="XPLockOther")
        cls.other_sheet = CharacterSheetFactory(character=cls.other_character)
        _link_account_to_sheet(cls.other_account, cls.other_character, cls.other_sheet)

        cls.resonance = ResonanceFactory()

        # Thread at level 0, TRAIT kind with trait value 100 → anchor cap = 100
        # _path_stage=3 → path cap = 30. effective cap = min(30, 100) = 30.
        # boundary_level=20 is within cap and above level=0, so the happy path works.
        cls.thread = ThreadFactory(
            owner=cls.sheet,
            resonance=cls.resonance,
            as_trait_thread=True,
            _trait_value=100,
            _path_stage=3,  # path cap = 30
            level=0,
        )

        # Seed the XP locked level row that costs 200 XP at boundary 20
        cls.xp_locked_level = ThreadXPLockedLevelFactory(level=20, xp_cost=200)

    def _url(self, pk):
        return reverse("magic:thread-cross-xp-lock", args=[pk])

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    def test_happy_path_creates_unlock_and_returns_data(self) -> None:
        """Owner with sufficient XP unlocks boundary; response has unlocked_level + xp_spent."""
        _give_xp(self.account, 500)
        self.client.force_authenticate(user=self.account)
        response = self.client.post(
            self._url(self.thread.pk), {"boundary_level": 20}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["unlocked_level"], 20)
        self.assertEqual(response.data["xp_spent"], 200)
        self.assertEqual(response.data["thread_id"], self.thread.pk)

        # Row was created in DB
        self.assertTrue(
            ThreadLevelUnlock.objects.filter(
                thread=self.thread,
                unlocked_level=20,
            ).exists()
        )

    # ------------------------------------------------------------------
    # Error cases
    # ------------------------------------------------------------------

    def test_xp_insufficient_returns_400(self) -> None:
        """Owner without enough XP gets HTTP 400."""
        _give_xp(self.account, 0)
        self.client.force_authenticate(user=self.account)
        response = self.client.post(
            self._url(self.thread.pk), {"boundary_level": 20}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # DRF raises ValidationError with a string → response.data is a list of ErrorDetails
        self.assertIn("You do not have enough XP for this.", response.data)

    def test_anchor_cap_exceeded_returns_400(self) -> None:
        """Boundary above effective cap → 400 with user_message."""
        # Use a thread with a very low trait value so anchor cap is tiny.
        # _path_stage=3 → path cap=30. _trait_value=5 → anchor cap=5.
        # effective cap = min(30, 5) = 5. boundary_level=20 > 5 → AnchorCapExceeded.
        low_cap_thread = ThreadFactory(
            owner=self.sheet,
            resonance=self.resonance,
            as_trait_thread=True,
            _trait_value=5,
            _path_stage=3,
            level=0,
        )
        _give_xp(self.account, 9999)
        self.client.force_authenticate(user=self.account)
        response = self.client.post(
            self._url(low_cap_thread.pk), {"boundary_level": 20}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # DRF raises ValidationError with a string → response.data is a list of ErrorDetails
        self.assertIn("This thread cannot grow beyond its anchor's strength.", response.data)

    def test_invalid_imbue_amount_returns_400_when_boundary_at_or_below_level(self) -> None:
        """Boundary at or below thread.level → 400."""
        # thread.level=0; boundary_level must be > 0 (boundary_level=0 fails min_value=1
        # serializer check, so use boundary_level=1 which is above 0 but below 20
        # boundary — but there's no XP locked level at 1, so it hits InvalidImbueAmount
        # "No XP lock defined for this boundary level."
        # Actually the service checks boundary_level <= thread.level first.
        # thread.level=0, boundary_level=1: 1 > 0 passes, then cap check, then
        # "no XP lock defined at 1" → InvalidImbueAmount.
        # To hit the boundary_level <= thread.level branch, use a thread at level 20
        # and try to cross 20 again (or lower).
        elevated_thread = ThreadFactory(
            owner=self.sheet,
            resonance=self.resonance,
            as_trait_thread=True,
            _trait_value=100,
            _path_stage=3,
            level=20,
        )
        _give_xp(self.account, 9999)
        self.client.force_authenticate(user=self.account)
        # boundary_level=20 == thread.level=20 → fails "must be above thread.level"
        response = self.client.post(
            self._url(elevated_thread.pk), {"boundary_level": 20}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # DRF raises ValidationError with a string → response.data is a list of ErrorDetails
        self.assertIn("Invalid imbue amount.", response.data)

    # ------------------------------------------------------------------
    # Permission
    # ------------------------------------------------------------------

    def test_non_owner_gets_404(self) -> None:
        """Non-owner cannot access thread — queryset filter returns 404."""
        self.client.force_authenticate(user=self.other_account)
        response = self.client.post(
            self._url(self.thread.pk), {"boundary_level": 20}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unauthenticated_gets_401_or_403(self) -> None:
        """Unauthenticated request is rejected."""
        response = self.client.post(
            self._url(self.thread.pk), {"boundary_level": 20}, format="json"
        )
        self.assertIn(
            response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
        )

    # ------------------------------------------------------------------
    # Idempotency
    # ------------------------------------------------------------------

    def test_idempotent_repeat_returns_same_unlock(self) -> None:
        """Calling cross_xp_lock twice with same boundary returns the same ThreadLevelUnlock."""
        # Create the unlock row directly (simulates first call already succeeded).
        existing = ThreadLevelUnlockFactory(
            thread=self.thread,
            unlocked_level=20,
            xp_spent=200,
        )
        _give_xp(self.account, 9999)
        self.client.force_authenticate(user=self.account)
        response = self.client.post(
            self._url(self.thread.pk), {"boundary_level": 20}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["unlocked_level"], 20)
        # The service is idempotent — it returns the existing row, not a new one.
        unlock_count = ThreadLevelUnlock.objects.filter(
            thread=self.thread,
            unlocked_level=20,
        ).count()
        self.assertEqual(unlock_count, 1)
        # Response unlock matches the existing row's xp_spent
        self.assertEqual(response.data["xp_spent"], existing.xp_spent)
