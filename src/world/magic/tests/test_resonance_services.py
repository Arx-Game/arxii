"""Tests for Resonance Pivot Spec A Phase 11 earn/spend services."""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.magic.exceptions import (
    AnchorCapExceeded,
    InvalidImbueAmount,
    ResonanceInsufficient,
    XPInsufficient,
)
from world.magic.factories import (
    CharacterResonanceFactory,
    CharacterSheetFactory,
    ResonanceFactory,
    ThreadFactory,
    ThreadLevelUnlockFactory,
    ThreadXPLockedLevelFactory,
)
from world.magic.models import ThreadLevelUnlock
from world.magic.services import (
    cross_thread_xp_lock,
    grant_resonance,
    spend_resonance_for_imbuing,
)

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
        if balance:
            CharacterResonanceFactory(
                character_sheet=sheet,
                resonance=res,
                balance=balance,
                lifetime_earned=balance,
            )
        else:
            # Create a zero-balance CR so the service can do the lookup
            CharacterResonanceFactory(
                character_sheet=sheet,
                resonance=res,
                balance=0,
                lifetime_earned=0,
            )
        return thread

    def test_sub_boundary_advance_costs_one_per_level(self) -> None:
        """Sub-10 levels each cost max((n-9)*100, 1)=1 dp.
        Thread at level 1, dev_points=0, balance=8, path_stage=10, trait_value=100.
        Levels 1→2…8→9 each cost 1 dp (8 levels, 8 dp used). Level 9→10 is a
        multiple-of-10 boundary but no XP lock entry exists → XP_LOCK? Actually
        stop before the 10-boundary: only spend 8 to get to 9. Then bucket=0,
        amount=8≠0 → blocked_by stays "NONE"."""
        thread = self._make_thread_with_balance(
            level=1, developed_points=0, balance=8, trait_value=100, path_stage=10
        )
        # cap = min(path_cap=10*10=100, anchor_cap=100) = 100
        result = spend_resonance_for_imbuing(thread.owner, thread, 8)
        # Levels 1→2, 2→3, ..., 8→9: 8 levels. Cost each = 1. Total = 8.
        # After advancing to 9, bucket=0 < cost(9→10)=1 (max((9-9)*100,1)=1).
        # amount=8≠0 → blocked_by stays "NONE".
        self.assertEqual(result.levels_gained, 8)
        self.assertEqual(result.new_level, 9)
        self.assertEqual(result.new_developed_points, 0)
        self.assertEqual(result.blocked_by, "NONE")

    def test_xp_lock_blocks_boundary_crossing(self) -> None:
        """Level 19, bucket=1100 (cost 19→20 = max((19-9)*100,1)=1000).
        20%10==0, XP lock for 20 exists, no unlock → blocked_by="XP_LOCK"."""
        thread = self._make_thread_with_balance(
            level=19, developed_points=1100, balance=0, trait_value=100, path_stage=10
        )
        ThreadXPLockedLevelFactory(level=20, xp_cost=200)
        result = spend_resonance_for_imbuing(thread.owner, thread, 0)
        self.assertEqual(result.new_level, 19)
        self.assertEqual(result.blocked_by, "XP_LOCK")

    def test_xp_lock_unlocked_permits_boundary_crossing(self) -> None:
        """Same as above but ThreadLevelUnlock for 20 exists.
        Advances to 20 (cost 1000, bucket 1100→100). Next cost = max((20-9)*100,1)=1100,
        bucket=100 < 1100, amount=0 → blocked_by="INSUFFICIENT_BUCKET"."""
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
        """Thread at effective cap already → raises AnchorCapExceeded immediately.
        path_stage=10 → path_cap=100. trait_value=15 → anchor_cap=15.
        effective_cap=15, level=15 → at cap."""
        thread = self._make_thread_with_balance(
            level=15, developed_points=0, balance=100, trait_value=15, path_stage=10
        )
        with self.assertRaises(AnchorCapExceeded):
            spend_resonance_for_imbuing(thread.owner, thread, 100)

    def test_insufficient_balance_raises(self) -> None:
        """balance=0, amount=50 → raises ResonanceInsufficient."""
        thread = self._make_thread_with_balance(
            level=10, developed_points=0, balance=0, trait_value=100, path_stage=10
        )
        with self.assertRaises(ResonanceInsufficient):
            spend_resonance_for_imbuing(thread.owner, thread, 50)

    def test_greedy_multi_level_when_bucket_overflows(self) -> None:
        """Thread at level 10, dev_points=0, balance=600, spend 600.
        Cost 10→11=100, 11→12=200, 12→13=300. Total=600. → level=13, dp=0."""
        thread = self._make_thread_with_balance(
            level=10, developed_points=0, balance=600, trait_value=100, path_stage=10
        )
        result = spend_resonance_for_imbuing(thread.owner, thread, 600)
        self.assertEqual(result.new_level, 13)
        self.assertEqual(result.new_developed_points, 0)
        self.assertEqual(result.levels_gained, 3)

    def test_amount_zero_drains_existing_bucket(self) -> None:
        """Thread at level 10, dev_points=600, spend 0.
        Cost 10→11=100 (bucket 500), 11→12=200 (bucket 300),
        12→13=300 (bucket 0). All advance. → level=13, dp=0.
        amount=0 → blocked_by="INSUFFICIENT_BUCKET" at break."""
        thread = self._make_thread_with_balance(
            level=10, developed_points=600, balance=0, trait_value=100, path_stage=10
        )
        result = spend_resonance_for_imbuing(thread.owner, thread, 0)
        self.assertEqual(result.new_level, 13)
        self.assertEqual(result.new_developed_points, 0)
        self.assertEqual(result.levels_gained, 3)
        self.assertEqual(result.blocked_by, "INSUFFICIENT_BUCKET")

    def test_wrong_owner_raises(self) -> None:
        """Thread owner != character_sheet → raises InvalidImbueAmount."""
        thread = self._make_thread_with_balance(
            level=10, developed_points=0, balance=100, trait_value=100, path_stage=10
        )
        other_sheet = CharacterSheetFactory()
        with self.assertRaises(InvalidImbueAmount):
            spend_resonance_for_imbuing(other_sheet, thread, 100)


# =============================================================================
# 11.3 — cross_thread_xp_lock
# =============================================================================


class CrossThreadXpLockTests(TestCase):
    def _make_thread_with_xp(
        self,
        thread_level: int = 10,
        xp_available: int = 500,
        trait_value: int = 100,
        path_stage: int = 10,
    ) -> tuple[Thread, ExperiencePointsData]:  # type: ignore[name-defined]
        """Helper: thread + seeded XP on an account linked to the character."""
        from evennia.objects.models import ObjectDB

        from world.progression.models.rewards import ExperiencePointsData

        account = AccountFactory()
        sheet = CharacterSheetFactory(_path_stage=path_stage)
        # Link the account to the character (Evennia pattern)
        sheet.character.account = account
        # Persist by adding to the M2M through AccountDB
        ObjectDB.objects.filter(pk=sheet.character.pk).update()
        # Use the Evennia API to link account to character
        account.characters.add(sheet.character)

        thread = ThreadFactory(
            owner=sheet,
            resonance=ResonanceFactory(),
            level=thread_level,
            _trait_value=trait_value,
        )
        xp_tracker, _ = ExperiencePointsData.objects.get_or_create(
            account=account,
            defaults={"total_earned": xp_available, "total_spent": 0},
        )
        xp_tracker.total_earned = xp_available
        xp_tracker.total_spent = 0
        xp_tracker.save(update_fields=["total_earned", "total_spent"])
        return thread, xp_tracker

    def test_pays_xp_creates_unlock_row(self) -> None:
        thread, xp_tracker = self._make_thread_with_xp(thread_level=10, xp_available=500)
        ThreadXPLockedLevelFactory(level=20, xp_cost=200)
        unlock = cross_thread_xp_lock(thread.owner, thread, 20)
        self.assertEqual(unlock.unlocked_level, 20)
        self.assertEqual(unlock.xp_spent, 200)
        xp_tracker.refresh_from_db()
        self.assertEqual(xp_tracker.current_available, 300)

    def test_idempotent_double_unlock(self) -> None:
        thread, xp_tracker = self._make_thread_with_xp(thread_level=10, xp_available=500)
        ThreadXPLockedLevelFactory(level=20, xp_cost=200)
        unlock1 = cross_thread_xp_lock(thread.owner, thread, 20)
        unlock2 = cross_thread_xp_lock(thread.owner, thread, 20)
        self.assertEqual(unlock1.pk, unlock2.pk)
        # XP only deducted once
        xp_tracker.refresh_from_db()
        self.assertEqual(xp_tracker.current_available, 300)
        self.assertEqual(
            ThreadLevelUnlock.objects.filter(thread=thread, unlocked_level=20).count(), 1
        )

    def test_insufficient_xp_raises(self) -> None:
        thread, _ = self._make_thread_with_xp(thread_level=10, xp_available=50)
        ThreadXPLockedLevelFactory(level=20, xp_cost=200)
        with self.assertRaises(XPInsufficient):
            cross_thread_xp_lock(thread.owner, thread, 20)

    def test_boundary_above_effective_cap_raises(self) -> None:
        # trait_value=20 → anchor_cap=20. path_stage=2 → path_cap=20.
        # effective_cap=20. boundary=30 > 20 → AnchorCapExceeded.
        thread, _ = self._make_thread_with_xp(
            thread_level=10, xp_available=500, trait_value=20, path_stage=2
        )
        ThreadXPLockedLevelFactory(level=30, xp_cost=200)
        with self.assertRaises(AnchorCapExceeded):
            cross_thread_xp_lock(thread.owner, thread, 30)


# =============================================================================
# 11.4 — weave_thread, update_thread_narrative, helper queries
# =============================================================================
