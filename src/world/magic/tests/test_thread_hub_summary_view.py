"""Tests for ThreadHubSummaryView (GET /api/magic/thread-hub-summary/).

Covers:
- Empty character (no threads, no balances) returns the empty shape.
- Character with ready/near-xp-lock/blocked threads and a TRAIT weaving unlock.
- Auth required (unauthenticated → 401/403).
- Alt-guard: account with multiple active tenures and ?character_sheet_id= resolves
  correctly; without it returns 400.
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from evennia_extensions.models import PlayerData
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import TargetKind
from world.magic.factories import (
    CharacterResonanceFactory,
    CharacterThreadWeavingUnlockFactory,
    ResonanceFactory,
    ThreadFactory,
    ThreadWeavingUnlockFactory,
    ThreadXPLockedLevelFactory,
)
from world.roster.factories import RosterEntryFactory, RosterTenureFactory


def _link_account_to_sheet(account, character, sheet):
    """Tie an AccountDB to a CharacterSheet via an active RosterTenure.

    Reuses an existing PlayerData row if the account already has one — this
    supports linking multiple active tenures to the same account for alt-guard
    tests, since PlayerData has a one-to-one constraint with Account.
    """
    character.account = account
    account.characters.add(character)
    player_data, _ = PlayerData.objects.get_or_create(account=account)
    return RosterTenureFactory(
        roster_entry=RosterEntryFactory(character_sheet=sheet),
        player_data=player_data,
    )


_URL = "/api/magic/thread-hub-summary/"


class ThreadHubSummaryEmptyCharacterTests(APITestCase):
    """Empty character returns the empty shape with all TargetKind keys False."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory(username="hub_empty_account")
        cls.character = CharacterFactory(db_key="HubEmptyChar")
        cls.sheet = CharacterSheetFactory(character=cls.character)
        _link_account_to_sheet(cls.account, cls.character, cls.sheet)

    def test_empty_character_returns_expected_shape(self) -> None:
        self.client.force_authenticate(user=self.account)
        response = self.client.get(_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        data = response.data
        self.assertEqual(data["balances"], [])
        self.assertEqual(data["ready_thread_ids"], [])
        self.assertEqual(data["near_xp_lock_thread_ids"], [])
        self.assertEqual(data["blocked_thread_ids"], [])

        # Every TargetKind must appear and must be False for an empty character.
        eligibility = data["weaving_eligibility"]
        for kind in TargetKind:
            self.assertIn(kind.value, eligibility, f"Missing TargetKind.{kind.name}")
            self.assertFalse(eligibility[kind.value], f"Expected False for {kind.name}")


class ThreadHubSummaryPopulatedTests(APITestCase):
    """Character with threads, balances, and a TRAIT weaving unlock."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory(username="hub_populated_account")
        cls.character = CharacterFactory(db_key="HubPopulatedChar")
        cls.sheet = CharacterSheetFactory(character=cls.character)
        _link_account_to_sheet(cls.account, cls.character, cls.sheet)

        cls.resonance = ResonanceFactory()

        # Resonance balance row.
        cls.cr = CharacterResonanceFactory(
            character_sheet=cls.sheet,
            resonance=cls.resonance,
            balance=25,
            lifetime_earned=50,
            flavor_text="fire and ash",
        )

        # --- ready-to-imbue thread ---
        # level=0 (below any cap), balance=25 above 0 → imbue_ready
        cls.ready_thread = ThreadFactory(
            owner=cls.sheet,
            resonance=cls.resonance,
            as_trait_thread=True,
            _trait_value=100,
            _path_stage=3,  # path cap=30; anchor cap=100 → effective=30
            level=0,
            developed_points=0,
        )

        # --- near-xp-lock thread ---
        # level=0, next_boundary=10.  Seed ThreadXPLockedLevel at boundary 10.
        # dp_needed = 10 (each level 0-9 costs 1 dp since (n-9)*100 ≤ 0).
        # With developed_points=5: dp_to_boundary = 10 - 5 = 5, within 100.
        cls.xp_locked = ThreadXPLockedLevelFactory(level=10, xp_cost=150)
        cls.near_thread = ThreadFactory(
            owner=cls.sheet,
            resonance=cls.resonance,
            as_trait_thread=True,
            _trait_value=100,
            _path_stage=3,
            level=0,
            developed_points=5,
        )

        # --- blocked thread (level == effective cap) ---
        # _trait_value=5 → anchor cap=5; _path_stage=3 → path cap=30 → effective=5.
        # level=5 == effective cap → blocked.
        cls.blocked_thread = ThreadFactory(
            owner=cls.sheet,
            resonance=cls.resonance,
            as_trait_thread=True,
            _trait_value=5,
            _path_stage=3,
            level=5,
            developed_points=0,
        )

        # --- TRAIT weaving unlock ---
        cls.unlock = ThreadWeavingUnlockFactory(target_kind=TargetKind.TRAIT)
        CharacterThreadWeavingUnlockFactory(
            character=cls.sheet,
            unlock=cls.unlock,
        )

    def test_balances_present(self) -> None:
        self.client.force_authenticate(user=self.account)
        response = self.client.get(_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        balances = response.data["balances"]
        self.assertEqual(len(balances), 1)
        b = balances[0]
        self.assertEqual(b["resonance_id"], self.resonance.pk)
        self.assertEqual(b["balance"], 25)
        self.assertEqual(b["lifetime_earned"], 50)
        self.assertEqual(b["flavor_text"], "fire and ash")

    def test_ready_thread_id_present(self) -> None:
        self.client.force_authenticate(user=self.account)
        response = self.client.get(_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        self.assertIn(self.ready_thread.pk, response.data["ready_thread_ids"])

    def test_near_xp_lock_entry_present(self) -> None:
        self.client.force_authenticate(user=self.account)
        response = self.client.get(_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        near = response.data["near_xp_lock_thread_ids"]
        # Should contain an entry for near_thread
        near_ids = [entry["thread_id"] for entry in near]
        self.assertIn(self.near_thread.pk, near_ids)
        # Verify xp_cost and boundary_level fields
        near_entry = next(e for e in near if e["thread_id"] == self.near_thread.pk)
        self.assertEqual(near_entry["xp_cost"], 150)
        self.assertEqual(near_entry["boundary_level"], 10)

    def test_blocked_thread_id_present(self) -> None:
        self.client.force_authenticate(user=self.account)
        response = self.client.get(_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        self.assertIn(self.blocked_thread.pk, response.data["blocked_thread_ids"])

    def test_trait_weaving_eligibility_true(self) -> None:
        self.client.force_authenticate(user=self.account)
        response = self.client.get(_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        eligibility = response.data["weaving_eligibility"]
        self.assertTrue(eligibility[TargetKind.TRAIT.value])

    def test_all_target_kinds_present_in_eligibility(self) -> None:
        self.client.force_authenticate(user=self.account)
        response = self.client.get(_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        eligibility = response.data["weaving_eligibility"]
        for kind in TargetKind:
            self.assertIn(kind.value, eligibility, f"Missing TargetKind.{kind.name}")


class ThreadHubSummaryAuthTests(APITestCase):
    """Unauthenticated requests are rejected."""

    def test_unauthenticated_is_rejected(self) -> None:
        response = self.client.get(_URL)
        self.assertIn(
            response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
        )


class ThreadHubSummaryAltGuardTests(APITestCase):
    """Alt-guard: multiple active tenures require explicit character_sheet_id."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory(username="hub_altguard_account")

        # First character/sheet
        cls.character1 = CharacterFactory(db_key="HubAltChar1")
        cls.sheet1 = CharacterSheetFactory(character=cls.character1)
        _link_account_to_sheet(cls.account, cls.character1, cls.sheet1)

        # Second character/sheet — same account → multiple active tenures
        cls.character2 = CharacterFactory(db_key="HubAltChar2")
        cls.sheet2 = CharacterSheetFactory(character=cls.character2)
        _link_account_to_sheet(cls.account, cls.character2, cls.sheet2)

    def test_multiple_tenures_without_sheet_id_returns_400(self) -> None:
        self.client.force_authenticate(user=self.account)
        response = self.client.get(_URL)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_multiple_tenures_with_explicit_sheet_id_returns_200(self) -> None:
        self.client.force_authenticate(user=self.account)
        response = self.client.get(_URL, {"character_sheet_id": self.sheet1.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
