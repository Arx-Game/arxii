"""Tests for Resonance Pivot Spec A Phase 11 earn/spend services."""

from __future__ import annotations

from django.test import TestCase
from evennia.objects.models import ObjectDB

from evennia_extensions.factories import AccountFactory
from world.magic.constants import TargetKind
from world.magic.exceptions import (
    AnchorCapExceeded,
    InvalidImbueAmount,
    ResonanceInsufficient,
    WeavingUnlockMissing,
    XPInsufficient,
)
from world.magic.factories import (
    CharacterResonanceFactory,
    CharacterSheetFactory,
    CharacterThreadWeavingUnlockFactory,
    FacetFactory,
    ResonanceFactory,
    ThreadFactory,
    ThreadLevelUnlockFactory,
    ThreadWeavingUnlockFactory,
    ThreadXPLockedLevelFactory,
)
from world.magic.models import (
    Thread,
    ThreadLevelUnlock,
)
from world.magic.services import (
    cross_thread_xp_lock,
    grant_resonance,
    imbue_ready_threads,
    near_xp_lock_threads,
    spend_resonance_for_imbuing,
    threads_blocked_by_cap,
    update_thread_narrative,
    weave_thread,
)
from world.progression.models.rewards import ExperiencePointsData
from world.traits.factories import TraitFactory

# =============================================================================
# 11.1 — grant_resonance
# =============================================================================


class GrantResonanceTests(TestCase):
    def test_staff_grant_writes_ledger_row(self) -> None:
        from world.magic.constants import GainSource
        from world.magic.models import ResonanceGrant

        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        cr = grant_resonance(sheet, res, 5, source=GainSource.STAFF_GRANT)
        self.assertEqual(cr.balance, 5)
        self.assertEqual(cr.lifetime_earned, 5)
        self.assertEqual(ResonanceGrant.objects.filter(character_sheet=sheet).count(), 1)
        grant = ResonanceGrant.objects.get(character_sheet=sheet)
        self.assertEqual(grant.amount, 5)
        self.assertEqual(grant.source, GainSource.STAFF_GRANT)

    def test_residence_grant_requires_aura_profile(self) -> None:
        from world.magic.constants import GainSource

        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        with self.assertRaises(ValueError):
            grant_resonance(sheet, res, 1, source=GainSource.ROOM_RESIDENCE)

    def test_residence_grant_happy_path(self) -> None:
        from world.magic.constants import GainSource
        from world.magic.factories import RoomAuraProfileFactory
        from world.magic.models import ResonanceGrant

        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        aura = RoomAuraProfileFactory()
        cr = grant_resonance(
            sheet,
            res,
            2,
            source=GainSource.ROOM_RESIDENCE,
            room_aura_profile=aura,
        )
        self.assertEqual(cr.balance, 2)
        self.assertEqual(ResonanceGrant.objects.filter(character_sheet=sheet).count(), 1)

    def test_invalid_amount_raises(self) -> None:
        from world.magic.constants import GainSource

        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        with self.assertRaises(InvalidImbueAmount):
            grant_resonance(sheet, res, 0, source=GainSource.STAFF_GRANT)

    def test_scene_entry_grant_writes_ledger(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.constants import GainSource
        from world.magic.factories import (
            ResonanceFactory,
            SceneEntryEndorsementFactory,
        )
        from world.magic.models import ResonanceGrant
        from world.magic.services.resonance import grant_resonance

        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        endorsement = SceneEntryEndorsementFactory(endorsee_sheet=sheet, resonance=res)
        cr = grant_resonance(
            sheet,
            res,
            4,
            source=GainSource.SCENE_ENTRY,
            scene_entry_endorsement=endorsement,
        )
        self.assertEqual(cr.balance, 4)
        grant = ResonanceGrant.objects.get(character_sheet=sheet)
        self.assertEqual(grant.source_scene_entry_endorsement, endorsement)
        self.assertEqual(grant.source, GainSource.SCENE_ENTRY)

    def test_pose_endorsement_grant_writes_ledger(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.constants import GainSource
        from world.magic.factories import (
            PoseEndorsementFactory,
            ResonanceFactory,
        )
        from world.magic.models import ResonanceGrant
        from world.magic.services.resonance import grant_resonance

        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        endorsement = PoseEndorsementFactory(endorsee_sheet=sheet, resonance=res)
        cr = grant_resonance(
            sheet,
            res,
            3,
            source=GainSource.POSE_ENDORSEMENT,
            pose_endorsement=endorsement,
        )
        self.assertEqual(cr.balance, 3)
        grant = ResonanceGrant.objects.get(character_sheet=sheet)
        self.assertEqual(grant.source_pose_endorsement, endorsement)
        self.assertEqual(grant.source, GainSource.POSE_ENDORSEMENT)


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
    ) -> Thread:
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
    ) -> tuple[Thread, ExperiencePointsData]:
        """Helper: thread + seeded XP on an account linked to the character."""
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


class WeaveThreadTests(TestCase):
    def test_weave_thread_trait_happy_path(self) -> None:
        """Character with TRAIT weaving unlock can create a TRAIT thread."""
        trait = TraitFactory()
        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        # Create weaving unlock for this trait
        unlock = ThreadWeavingUnlockFactory(target_kind=TargetKind.TRAIT, unlock_trait=trait)
        CharacterThreadWeavingUnlockFactory(character=sheet, unlock=unlock, xp_spent=100)

        thread = weave_thread(sheet, TargetKind.TRAIT, trait, res, name="My Thread")
        self.assertEqual(thread.owner, sheet)
        self.assertEqual(thread.resonance, res)
        self.assertEqual(thread.target_kind, TargetKind.TRAIT)
        self.assertEqual(thread.target_trait, trait)
        self.assertEqual(thread.name, "My Thread")
        self.assertEqual(thread.level, 0)

    def test_weave_thread_no_unlock_raises(self) -> None:
        """Character without weaving unlock → raises WeavingUnlockMissing."""
        trait = TraitFactory()
        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        with self.assertRaises(WeavingUnlockMissing):
            weave_thread(sheet, TargetKind.TRAIT, trait, res)

    def test_weave_thread_facet(self) -> None:
        """Character with global FACET weaving unlock can create a FACET thread."""
        from world.magic.models import ThreadWeavingUnlock

        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        facet = FacetFactory()
        # Single global unlock for FACET kind — all FK args NULL, bypasses full_clean()
        unlock = ThreadWeavingUnlock.objects.create(target_kind=TargetKind.FACET, xp_cost=100)
        CharacterThreadWeavingUnlockFactory(character=sheet, unlock=unlock, xp_spent=100)

        thread = weave_thread(sheet, TargetKind.FACET, facet, res, name="Silk Thread")
        self.assertEqual(thread.owner, sheet)
        self.assertEqual(thread.resonance, res)
        self.assertEqual(thread.target_kind, TargetKind.FACET)
        self.assertEqual(thread.target_facet, facet)
        self.assertEqual(thread.name, "Silk Thread")
        self.assertEqual(thread.level, 0)

    def test_weave_thread_facet_no_unlock_raises(self) -> None:
        """Character without FACET weaving unlock → raises WeavingUnlockMissing."""
        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        facet = FacetFactory()
        with self.assertRaises(WeavingUnlockMissing):
            weave_thread(sheet, TargetKind.FACET, facet, res)

    def test_weave_thread_covenant_role_never_held_raises(self) -> None:
        """Character who has never held the role → raises CovenantRoleNeverHeldError."""
        from world.covenants.exceptions import CovenantRoleNeverHeldError
        from world.covenants.factories import CovenantRoleFactory

        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        role = CovenantRoleFactory()
        with self.assertRaises(CovenantRoleNeverHeldError):
            weave_thread(sheet, TargetKind.COVENANT_ROLE, role, res)

    def test_weave_thread_covenant_role_with_historical_role_succeeds(self) -> None:
        """Character who has held the role (active or ended) can weave a COVENANT_ROLE thread."""
        from world.covenants.factories import CharacterCovenantRoleFactory, CovenantRoleFactory

        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        role = CovenantRoleFactory()
        CharacterCovenantRoleFactory(character_sheet=sheet, covenant_role=role)

        thread = weave_thread(sheet, TargetKind.COVENANT_ROLE, role, res, name="Vanguard Thread")
        self.assertEqual(thread.owner, sheet)
        self.assertEqual(thread.resonance, res)
        self.assertEqual(thread.target_kind, TargetKind.COVENANT_ROLE)
        self.assertEqual(thread.target_covenant_role, role)
        self.assertEqual(thread.name, "Vanguard Thread")
        self.assertEqual(thread.level, 0)


class UpdateThreadNarrativeTests(TestCase):
    def test_update_name_and_description(self) -> None:
        thread = ThreadFactory(name="Old", description="Old desc")
        result = update_thread_narrative(thread, name="New", description="New desc")
        self.assertEqual(result.name, "New")
        self.assertEqual(result.description, "New desc")
        thread.refresh_from_db()
        self.assertEqual(thread.name, "New")

    def test_update_name_only(self) -> None:
        thread = ThreadFactory(name="Old", description="Keep")
        update_thread_narrative(thread, name="Changed")
        thread.refresh_from_db()
        self.assertEqual(thread.name, "Changed")
        self.assertEqual(thread.description, "Keep")

    def test_update_nothing_is_noop(self) -> None:
        """Calling with no kwargs returns thread unchanged."""
        thread = ThreadFactory(name="Same", description="Same desc")
        update_thread_narrative(thread)
        thread.refresh_from_db()
        self.assertEqual(thread.name, "Same")


class ImbuReadyThreadsTests(TestCase):
    def test_returns_thread_with_balance_below_cap(self) -> None:
        """Thread at level 5 with cap=10 (path_cap=10, anchor_cap=100) and balance > 0."""
        sheet = CharacterSheetFactory(_path_stage=1)  # path_cap = max(1,1)*10 = 10
        res = ResonanceFactory()
        # trait_value=100, so anchor_cap=100, effective_cap=min(10,100)=10. level=5<10
        thread = ThreadFactory(owner=sheet, resonance=res, level=5, _trait_value=100)
        CharacterResonanceFactory(
            character_sheet=sheet, resonance=res, balance=50, lifetime_earned=50
        )
        result = imbue_ready_threads(sheet)
        self.assertIn(thread, result)

    def test_excludes_thread_at_cap(self) -> None:
        """Thread at effective cap is excluded."""
        sheet = CharacterSheetFactory(_path_stage=1)  # path_cap=10
        res = ResonanceFactory()
        # trait_value=100, effective_cap=10, level=10 → at cap
        thread = ThreadFactory(owner=sheet, resonance=res, level=10, _trait_value=100)
        CharacterResonanceFactory(
            character_sheet=sheet, resonance=res, balance=50, lifetime_earned=50
        )
        result = imbue_ready_threads(sheet)
        self.assertNotIn(thread, result)

    def test_excludes_thread_with_zero_balance(self) -> None:
        """Thread with zero balance is excluded."""
        sheet = CharacterSheetFactory(_path_stage=1)
        res = ResonanceFactory()
        ThreadFactory(owner=sheet, resonance=res, level=5, _trait_value=100)
        CharacterResonanceFactory(
            character_sheet=sheet, resonance=res, balance=0, lifetime_earned=0
        )
        result = imbue_ready_threads(sheet)
        self.assertEqual(result, [])


class NearXpLockThreadsTests(TestCase):
    def test_returns_thread_near_boundary(self) -> None:
        """Thread at level 10, dev_points=5400, next boundary=20.
        dp_needed = sum(max((n-9)*100,1) for n in range(10,20))
                  = 100+200+300+400+500+600+700+800+900+1000 = 5500
        dp_to_boundary = 5500-5400=100 → within=100 → included."""
        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        thread = ThreadFactory(
            owner=sheet, resonance=res, level=10, developed_points=5400, _trait_value=100
        )
        ThreadXPLockedLevelFactory(level=20, xp_cost=200)
        result = near_xp_lock_threads(sheet, within=100)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].thread, thread)
        self.assertEqual(result[0].boundary_level, 20)
        self.assertEqual(result[0].dev_points_to_boundary, 100)

    def test_excludes_already_unlocked_boundary(self) -> None:
        """Boundary already unlocked is excluded."""
        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        thread = ThreadFactory(
            owner=sheet, resonance=res, level=10, developed_points=5400, _trait_value=100
        )
        ThreadXPLockedLevelFactory(level=20, xp_cost=200)
        ThreadLevelUnlockFactory(thread=thread, unlocked_level=20, xp_spent=200)
        result = near_xp_lock_threads(sheet, within=100)
        self.assertEqual(result, [])


class ThreadsBlockedByCapTests(TestCase):
    def test_returns_thread_at_cap(self) -> None:
        """Thread at effective_cap is returned."""
        sheet = CharacterSheetFactory(_path_stage=1)  # path_cap=10
        res = ResonanceFactory()
        # trait_value=100, effective_cap=min(10,100)=10, level=10 → at cap
        thread = ThreadFactory(owner=sheet, resonance=res, level=10, _trait_value=100)
        result = threads_blocked_by_cap(sheet)
        self.assertIn(thread, result)

    def test_excludes_thread_below_cap(self) -> None:
        """Thread below effective_cap is excluded."""
        sheet = CharacterSheetFactory(_path_stage=1)  # path_cap=10
        res = ResonanceFactory()
        # level=5 < cap=10 → below cap
        thread = ThreadFactory(owner=sheet, resonance=res, level=5, _trait_value=100)
        result = threads_blocked_by_cap(sheet)
        self.assertNotIn(thread, result)


# =============================================================================
# Gate 10.6 — ProtagonismLockedError for resonance currency spends
# =============================================================================


class ProtagonismLockResonanceSpendTests(TestCase):
    """spend_resonance_for_imbuing and spend_resonance_for_pull raise ProtagonismLockedError
    when the character's sheet is at terminal corruption stage."""

    def _make_subsumed_sheet(self):
        """Return a CharacterSheet at corruption stage 5 (protagonism locked)."""
        from world.magic.factories import with_corruption_at_stage

        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        with_corruption_at_stage(sheet, res, stage=5)
        sheet.__dict__.pop("is_protagonism_locked", None)
        return sheet

    def test_spend_resonance_for_imbuing_blocked(self) -> None:
        from world.magic.exceptions import ProtagonismLockedError
        from world.magic.services import spend_resonance_for_imbuing

        sheet = self._make_subsumed_sheet()
        res = ResonanceFactory()
        CharacterResonanceFactory(character_sheet=sheet, resonance=res, balance=100)
        thread = ThreadFactory(owner=sheet, resonance=res)

        with self.assertRaises(ProtagonismLockedError):
            spend_resonance_for_imbuing(sheet, thread, 10)

    def test_spend_resonance_for_pull_blocked(self) -> None:
        from world.magic.exceptions import ProtagonismLockedError
        from world.magic.services import spend_resonance_for_pull
        from world.magic.types import PullActionContext

        sheet = self._make_subsumed_sheet()
        res = ResonanceFactory()
        CharacterResonanceFactory(character_sheet=sheet, resonance=res, balance=100)
        thread = ThreadFactory(owner=sheet, resonance=res)

        ctx = PullActionContext()

        with self.assertRaises(ProtagonismLockedError):
            spend_resonance_for_pull(sheet, res, 1, [thread], ctx)
