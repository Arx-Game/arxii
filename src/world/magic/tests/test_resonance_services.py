"""Tests for Resonance Pivot Spec A Phase 11 earn/spend services."""

from __future__ import annotations

from django.test import TestCase

from world.magic.exceptions import (
    AnchorCapExceeded,
    InvalidImbueAmount,
    ResonanceInsufficient,
)
from world.magic.factories import (
    CharacterResonanceFactory,
    CharacterSheetFactory,
    ResonanceFactory,
    ThreadFactory,
    ThreadLevelUnlockFactory,
    ThreadXPLockedLevelFactory,
)
from world.magic.services import grant_resonance, spend_resonance_for_imbuing

# =============================================================================
# 11.1 — grant_resonance
# =============================================================================


class GrantResonanceTests(TestCase):
    def test_first_call_creates_row(self) -> None:
        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        cr = grant_resonance(sheet, res, 5, source="test")
        self.assertEqual(cr.balance, 5)
        self.assertEqual(cr.lifetime_earned, 5)

    def test_second_call_increments_both_fields(self) -> None:
        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        grant_resonance(sheet, res, 5, source="test")
        cr = grant_resonance(sheet, res, 7, source="test")
        self.assertEqual(cr.balance, 12)
        self.assertEqual(cr.lifetime_earned, 12)

    def test_zero_amount_rejected(self) -> None:
        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        with self.assertRaises(InvalidImbueAmount):
            grant_resonance(sheet, res, 0, source="test")


# =============================================================================
# 11.2 — spend_resonance_for_imbuing
# =============================================================================


class SpendResonanceForImbuingTests(TestCase):
    def _make_thread_with_balance(
        self,
        level: int = 10,
        developed_points: int = 0,
        balance: int = 0,
        trait_value: int = 100,
        path_stage: int = 10,
    ) -> Thread:  # type: ignore[name-defined]
        """Helper: trait thread with cap determined by path_stage and trait_value."""
        sheet = CharacterSheetFactory(_path_stage=path_stage)
        res = ResonanceFactory()
        thread = ThreadFactory(
            owner=sheet,
            resonance=res,
            level=level,
            developed_points=developed_points,
            _trait_value=trait_value,
        )
        CharacterResonanceFactory(
            character_sheet=sheet,
            resonance=res,
            balance=balance,
            lifetime_earned=balance,
        )
        return thread

    def test_sub_boundary_advance_costs_one_per_level(self) -> None:
        """Sub-10 levels each cost max((n-9)*100, 1)=1 dp.
        Thread at level 1, dev_points=0, balance=8, path_stage=10.
        Levels 1->2...8->9 each cost 1 dp. After 9, bucket=0 -> stop.
        amount=8 != 0 -> blocked_by stays "NONE"."""
        thread = self._make_thread_with_balance(
            level=1, developed_points=0, balance=8, trait_value=100, path_stage=10
        )
        result = spend_resonance_for_imbuing(thread.owner, thread, 8)
        self.assertEqual(result.levels_gained, 8)
        self.assertEqual(result.new_level, 9)
        self.assertEqual(result.new_developed_points, 0)
        self.assertEqual(result.blocked_by, "NONE")

    def test_xp_lock_blocks_boundary_crossing(self) -> None:
        """Level 19, bucket=1100. 20%10==0, lock exists, no unlock -> XP_LOCK."""
        thread = self._make_thread_with_balance(
            level=19, developed_points=1100, balance=0, trait_value=100, path_stage=10
        )
        ThreadXPLockedLevelFactory(level=20, xp_cost=200)
        result = spend_resonance_for_imbuing(thread.owner, thread, 0)
        self.assertEqual(result.new_level, 19)
        self.assertEqual(result.blocked_by, "XP_LOCK")

    def test_xp_lock_unlocked_permits_boundary_crossing(self) -> None:
        """Unlock exists for 20. Advances to 20, then INSUFFICIENT_BUCKET."""
        thread = self._make_thread_with_balance(
            level=19, developed_points=1100, balance=0, trait_value=100, path_stage=10
        )
        ThreadXPLockedLevelFactory(level=20, xp_cost=200)
        ThreadLevelUnlockFactory(thread=thread, unlocked_level=20, xp_spent=200)
        result = spend_resonance_for_imbuing(thread.owner, thread, 0)
        self.assertEqual(result.new_level, 20)
        self.assertEqual(result.new_developed_points, 100)
        self.assertEqual(result.blocked_by, "INSUFFICIENT_BUCKET")

    def test_anchor_cap_exceeded_blocks(self) -> None:
        """Thread at effective cap -> raises AnchorCapExceeded."""
        thread = self._make_thread_with_balance(
            level=15, developed_points=0, balance=100, trait_value=15, path_stage=10
        )
        with self.assertRaises(AnchorCapExceeded):
            spend_resonance_for_imbuing(thread.owner, thread, 100)

    def test_insufficient_balance_raises(self) -> None:
        """balance=0, amount=50 -> raises ResonanceInsufficient."""
        thread = self._make_thread_with_balance(
            level=10, developed_points=0, balance=0, trait_value=100, path_stage=10
        )
        with self.assertRaises(ResonanceInsufficient):
            spend_resonance_for_imbuing(thread.owner, thread, 50)

    def test_greedy_multi_level_when_bucket_overflows(self) -> None:
        """Cost 10->11=100, 11->12=200, 12->13=300. Total=600 -> level=13, dp=0."""
        thread = self._make_thread_with_balance(
            level=10, developed_points=0, balance=600, trait_value=100, path_stage=10
        )
        result = spend_resonance_for_imbuing(thread.owner, thread, 600)
        self.assertEqual(result.new_level, 13)
        self.assertEqual(result.new_developed_points, 0)
        self.assertEqual(result.levels_gained, 3)

    def test_amount_zero_drains_existing_bucket(self) -> None:
        """dev_points=600, spend 0. Advances to 13, dp=0, INSUFFICIENT_BUCKET."""
        thread = self._make_thread_with_balance(
            level=10, developed_points=600, balance=0, trait_value=100, path_stage=10
        )
        result = spend_resonance_for_imbuing(thread.owner, thread, 0)
        self.assertEqual(result.new_level, 13)
        self.assertEqual(result.new_developed_points, 0)
        self.assertEqual(result.levels_gained, 3)
        self.assertEqual(result.blocked_by, "INSUFFICIENT_BUCKET")

    def test_wrong_owner_raises(self) -> None:
        """Thread owner != character_sheet -> raises InvalidImbueAmount."""
        thread = self._make_thread_with_balance(
            level=10, developed_points=0, balance=100, trait_value=100, path_stage=10
        )
        other_sheet = CharacterSheetFactory()
        with self.assertRaises(InvalidImbueAmount):
            spend_resonance_for_imbuing(other_sheet, thread, 100)
