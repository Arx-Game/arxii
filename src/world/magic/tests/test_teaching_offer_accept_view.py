"""Tests for ThreadWeavingTeachingOfferViewSet.accept action (Spec A §6.1).

POST /api/magic/teaching-offers/{id}/accept/

Covers:
- Happy path (in-Path learner): XP deducted == unlock.xp_cost; CharacterThreadWeavingUnlock
  created with correct xp_spent and teacher; teacher's banked AP reduced.
- Out-of-Path learner: XP deducted == unlock.xp_cost * unlock.out_of_path_multiplier.
- XPInsufficient: returns HTTP 400 with user_message.
- Alt guard (multiple active tenures, no learner_sheet_id): returns HTTP 400.
- Alt guard (multiple active tenures, valid learner_sheet_id): uses that sheet.
- Permission: unauthenticated returns 401.
- Listing: GET /api/magic/teaching-offers/ returns offers with effective_xp_cost_for_viewer.
- Listing alt-ambiguity: multi-tenure account without learner_sheet_id sees null.
"""

from __future__ import annotations

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from evennia_extensions.models import PlayerData
from world.action_points.models import ActionPointPool
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import (
    PendingAlterationFactory,
    ThreadWeavingTeachingOfferFactory,
    ThreadWeavingUnlockFactory,
)
from world.magic.models import CharacterThreadWeavingUnlock
from world.magic.types import AlterationGateError
from world.progression.models import ExperiencePointsData
from world.roster.factories import RosterEntryFactory, RosterTenureFactory


def _link_account_to_sheet(account, character, sheet):
    """Tie an AccountDB to a CharacterSheet via an active RosterTenure.

    Also sets character.account so that service functions navigate correctly.
    Returns the created RosterTenure.  Reuses an existing PlayerData row if the
    account already has one (supports linking multiple tenures to one account).
    """
    character.account = account
    account.characters.add(character)
    player_data, _ = PlayerData.objects.get_or_create(account=account)
    return RosterTenureFactory(
        roster_entry=RosterEntryFactory(character_sheet=sheet),
        player_data=player_data,
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


class TeachingOfferAcceptViewTests(APITestCase):
    """Tests for ThreadWeavingTeachingOfferViewSet.accept action."""

    @classmethod
    def setUpTestData(cls) -> None:
        # Learner account / character / sheet
        cls.learner_account = AccountFactory(username="teaching_offer_learner")
        cls.learner_character = CharacterFactory(db_key="TeachingLearner")
        cls.learner_sheet = CharacterSheetFactory(character=cls.learner_character)
        cls.learner_tenure = _link_account_to_sheet(
            cls.learner_account, cls.learner_character, cls.learner_sheet
        )

        # Teacher account / character / sheet / tenure
        cls.teacher_account = AccountFactory(username="teaching_offer_teacher")
        cls.teacher_character = CharacterFactory(db_key="TeachingTeacher")
        cls.teacher_sheet = CharacterSheetFactory(character=cls.teacher_character)
        cls.teacher_tenure = _link_account_to_sheet(
            cls.teacher_account, cls.teacher_character, cls.teacher_sheet
        )

        # An unlock with xp_cost=100 and out_of_path_multiplier=2.0.
        # No paths M2M set → Path-neutral (in-path cost by default).
        cls.unlock = ThreadWeavingUnlockFactory(xp_cost=100)

        # Teaching offer with banked_ap=5.
        cls.offer = ThreadWeavingTeachingOfferFactory(
            teacher=cls.teacher_tenure,
            unlock=cls.unlock,
            banked_ap=5,
        )

    def _accept_url(self, offer_pk):
        return reverse("magic:thread-weaving-teaching-offer-accept", args=[offer_pk])

    def _list_url(self):
        return reverse("magic:thread-weaving-teaching-offer-list")

    # ------------------------------------------------------------------
    # Happy path — in-Path learner
    # ------------------------------------------------------------------

    def test_happy_path_in_path_deducts_base_xp_cost(self) -> None:
        """In-Path learner: XP deducted equals unlock.xp_cost."""
        _give_xp(self.learner_account, 500)
        # Bank AP on teacher's pool so it can be consumed.
        teacher_pool = ActionPointPool.get_or_create_for_character(self.teacher_character)
        teacher_pool.regenerate(10)
        teacher_pool.bank(5)

        self.client.force_authenticate(user=self.learner_account)
        response = self.client.post(self._accept_url(self.offer.pk), {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        # Row created
        char_unlock = CharacterThreadWeavingUnlock.objects.filter(
            character=self.learner_sheet,
            unlock=self.unlock,
        ).first()
        self.assertIsNotNone(char_unlock)
        self.assertEqual(char_unlock.xp_spent, 100)
        self.assertEqual(char_unlock.teacher, self.teacher_tenure)

        # XP deducted
        xp = ExperiencePointsData.objects.get(account=self.learner_account)
        self.assertEqual(xp.current_available, 400)

        # Teacher's banked AP reduced
        teacher_pool.refresh_from_db()
        self.assertEqual(teacher_pool.banked, 0)

        # Response payload
        self.assertEqual(response.data["unlock_id"], self.unlock.pk)
        self.assertEqual(response.data["xp_spent"], 100)

    # ------------------------------------------------------------------
    # Out-of-Path learner
    # ------------------------------------------------------------------

    def test_out_of_path_learner_deducts_multiplied_cost(self) -> None:
        """Out-of-Path learner: XP deducted = unlock.xp_cost * out_of_path_multiplier."""
        # Create a separate unlock with paths set + multiplier=2.0
        from world.classes.factories import PathFactory

        path = PathFactory()
        out_of_path_unlock = ThreadWeavingUnlockFactory(xp_cost=50, out_of_path_multiplier=2.0)
        out_of_path_unlock.paths.add(path)

        # Learner has no path history → out-of-path → cost = 50 * 2.0 = 100
        offer = ThreadWeavingTeachingOfferFactory(
            teacher=self.teacher_tenure,
            unlock=out_of_path_unlock,
            banked_ap=0,
        )

        _give_xp(self.learner_account, 500)
        self.client.force_authenticate(user=self.learner_account)
        response = self.client.post(self._accept_url(offer.pk), {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["xp_spent"], 100)

        char_unlock = CharacterThreadWeavingUnlock.objects.filter(
            character=self.learner_sheet,
            unlock=out_of_path_unlock,
        ).first()
        self.assertIsNotNone(char_unlock)
        self.assertEqual(char_unlock.xp_spent, 100)

    # ------------------------------------------------------------------
    # XPInsufficient
    # ------------------------------------------------------------------

    def test_xp_insufficient_returns_400(self) -> None:
        """Learner without enough XP gets HTTP 400 with user_message."""
        _give_xp(self.learner_account, 0)
        self.client.force_authenticate(user=self.learner_account)
        response = self.client.post(self._accept_url(self.offer.pk), {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # DRF ValidationError from serializer.create → list of ErrorDetail
        self.assertIn("You do not have enough XP for this.", response.data)

    def test_open_mage_scar_returns_400_with_gate_message(self) -> None:
        """Learner with an open Mage Scar gets HTTP 400 with the gate user_message."""
        _give_xp(self.learner_account, 500)
        # Give teacher enough banked AP
        teacher_pool = ActionPointPool.get_or_create_for_character(self.teacher_character)
        teacher_pool.regenerate(10)
        teacher_pool.bank(5)
        PendingAlterationFactory(character=self.learner_sheet)

        self.client.force_authenticate(user=self.learner_account)
        response = self.client.post(self._accept_url(self.offer.pk), {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # The gate message must appear somewhere in the response
        self.assertIn(AlterationGateError.user_message, str(response.data))

    # ------------------------------------------------------------------
    # Alt guard — multiple active tenures
    # ------------------------------------------------------------------

    def test_alt_guard_multiple_tenures_no_sheet_id_returns_400(self) -> None:
        """Account with two active tenures and no learner_sheet_id gets 400."""
        # Create a second tenure for the learner account.
        alt_character = CharacterFactory(db_key="TeachingLearnerAlt")
        alt_sheet = CharacterSheetFactory(character=alt_character)
        _link_account_to_sheet(self.learner_account, alt_character, alt_sheet)

        _give_xp(self.learner_account, 500)
        self.client.force_authenticate(user=self.learner_account)
        response = self.client.post(self._accept_url(self.offer.pk), {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_alt_guard_multiple_tenures_with_valid_sheet_id_succeeds(self) -> None:
        """Account with two active tenures providing learner_sheet_id uses that sheet."""
        # Create a second tenure for a fresh alt account to avoid data coupling between tests.
        alt_account = AccountFactory(username="teaching_alt_account")
        alt_character1 = CharacterFactory(db_key="TeachingAltChar1")
        alt_sheet1 = CharacterSheetFactory(character=alt_character1)
        _link_account_to_sheet(alt_account, alt_character1, alt_sheet1)

        alt_character2 = CharacterFactory(db_key="TeachingAltChar2")
        alt_sheet2 = CharacterSheetFactory(character=alt_character2)
        _link_account_to_sheet(alt_account, alt_character2, alt_sheet2)

        # Create a separate offer for this test.
        alt_offer = ThreadWeavingTeachingOfferFactory(
            teacher=self.teacher_tenure,
            unlock=ThreadWeavingUnlockFactory(xp_cost=50),
            banked_ap=0,
        )

        _give_xp(alt_account, 500)
        self.client.force_authenticate(user=alt_account)
        response = self.client.post(
            self._accept_url(alt_offer.pk),
            {"learner_sheet_id": alt_sheet1.pk},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        char_unlock = CharacterThreadWeavingUnlock.objects.filter(
            character=alt_sheet1,
            unlock=alt_offer.unlock,
        ).first()
        self.assertIsNotNone(char_unlock)

    # ------------------------------------------------------------------
    # Permission
    # ------------------------------------------------------------------

    def test_unauthenticated_returns_401(self) -> None:
        """Unauthenticated request is rejected with 401 or 403."""
        response = self.client.post(self._accept_url(self.offer.pk), {}, format="json")
        self.assertIn(
            response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
        )

    # ------------------------------------------------------------------
    # Listing — effective_xp_cost_for_viewer
    # ------------------------------------------------------------------

    def test_listing_populates_effective_xp_cost_for_viewer(self) -> None:
        """GET listing includes effective_xp_cost_for_viewer for single-tenure accounts."""
        self.client.force_authenticate(user=self.learner_account)
        # Ensure only one active tenure for learner at this point in class setup.
        # (Tests using learner_account for alt-guard create alt tenures independently.)
        response = self.client.get(self._list_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        # Find the offer we created in setUpTestData
        results = response.data["results"]
        offer_data = next((r for r in results if r["id"] == self.offer.pk), None)
        self.assertIsNotNone(offer_data)
        # unlock.xp_cost=100, path-neutral → cost = 100
        self.assertEqual(offer_data["effective_xp_cost_for_viewer"], 100)

    def test_listing_alt_ambiguity_returns_null_effective_cost(self) -> None:
        """Multi-tenure account without learner_sheet_id query param sees null."""
        multi_account = AccountFactory(username="teaching_multi_tenure")
        char_a = CharacterFactory(db_key="MultiTenureA")
        sheet_a = CharacterSheetFactory(character=char_a)
        _link_account_to_sheet(multi_account, char_a, sheet_a)

        char_b = CharacterFactory(db_key="MultiTenureB")
        sheet_b = CharacterSheetFactory(character=char_b)
        _link_account_to_sheet(multi_account, char_b, sheet_b)

        self.client.force_authenticate(user=multi_account)
        response = self.client.get(self._list_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        results = response.data["results"]
        offer_data = next((r for r in results if r["id"] == self.offer.pk), None)
        self.assertIsNotNone(offer_data)
        self.assertIsNone(offer_data["effective_xp_cost_for_viewer"])

    # ------------------------------------------------------------------
    # N+1 regression — viewer sheet resolution fires once per list, not per row
    # ------------------------------------------------------------------

    def test_listing_viewer_sheet_resolution_does_not_grow_with_row_count(self) -> None:
        """Viewer sheet query fires once per request regardless of how many offers are listed.

        Creates 4 extra offers (all sharing the same unlock so paths M2M is the same
        object) then asserts that the CharacterSheet tenant-resolution query appears
        exactly once in the captured SQL — not once per row.
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        # Add 4 more offers all sharing the SAME unlock so the only variable
        # per-row query would be the viewer-sheet resolution (not unlock.paths).
        for _i in range(4):
            ThreadWeavingTeachingOfferFactory(
                teacher=self.teacher_tenure,
                unlock=self.unlock,
                banked_ap=0,
            )

        self.client.force_authenticate(user=self.learner_account)

        # Warm session/auth caches with a throwaway call.
        self.client.get(self._list_url())

        with CaptureQueriesContext(connection) as ctx:
            r = self.client.get(self._list_url())

        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(r.data["results"]), 5)

        # The viewer-sheet tenant-resolution query (CharacterSheet WHERE
        # roster_entry__tenures__player_data__account = ...) must appear AT MOST ONCE.
        viewer_sheet_queries = [
            q["sql"]
            for q in ctx.captured_queries
            if "character_sheets" in q["sql"] and "tenures" in q["sql"]
        ]
        self.assertLessEqual(
            len(viewer_sheet_queries),
            1,
            f"Viewer-sheet resolution query fired {len(viewer_sheet_queries)} times "
            f"(expected ≤1). Per-row N+1 detected.\n" + "\n".join(viewer_sheet_queries),
        )
