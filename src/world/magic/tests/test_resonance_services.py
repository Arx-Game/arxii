"""Tests for Resonance Pivot Spec A Phase 11 earn/spend services."""

from __future__ import annotations

from django.test import TestCase
from evennia.objects.models import ObjectDB

from evennia_extensions.factories import AccountFactory
from world.items.factories import ItemTemplateFactory
from world.magic.constants import TargetKind
from world.magic.exceptions import (
    AnchorCapExceeded,
    InvalidImbueAmount,
    WeavingUnlockMissing,
    XPInsufficient,
)
from world.magic.factories import (
    CharacterResonanceFactory,
    CharacterSheetFactory,
    CharacterThreadWeavingUnlockFactory,
    FacetFactory,
    PendingAlterationFactory,
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
    threads_blocked_by_cap,
    update_thread_narrative,
    weave_thread,
)
from world.magic.types import AlterationGateError
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

    def test_residence_grant_requires_room_profile(self) -> None:
        from world.magic.constants import GainSource

        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        with self.assertRaises(ValueError):
            grant_resonance(sheet, res, 1, source=GainSource.ROOM_RESIDENCE)

    def test_residence_grant_happy_path(self) -> None:
        from evennia_extensions.factories import RoomProfileFactory
        from world.magic.constants import GainSource
        from world.magic.models import ResonanceGrant

        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        rp = RoomProfileFactory()
        cr = grant_resonance(
            sheet,
            res,
            2,
            source=GainSource.ROOM_RESIDENCE,
            room_profile=rp,
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
# 11.3 — cross_thread_xp_lock
# =============================================================================


class _CrossXpLockSetupMixin:
    """Shared setup for cross_thread_xp_lock test classes (#898): builds a thread
    owned by a character whose account has seeded XP."""

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


class CrossThreadXpLockTests(_CrossXpLockSetupMixin, TestCase):
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
# 11.3b — cross_thread_xp_lock Mage Scar gate (#898)
# =============================================================================


class CrossThreadXpLockGateTests(_CrossXpLockSetupMixin, TestCase):
    """cross_thread_xp_lock must block characters with an open Mage Scar."""

    def test_open_pending_alteration_raises_alteration_gate_error(self) -> None:
        """Character with an OPEN PendingAlteration → AlterationGateError."""
        thread, _ = self._make_thread_with_xp(thread_level=10, xp_available=500)
        ThreadXPLockedLevelFactory(level=20, xp_cost=200)
        PendingAlterationFactory(character=thread.owner)

        with self.assertRaises(AlterationGateError):
            cross_thread_xp_lock(thread.owner, thread, 20)

    def test_open_pending_alteration_no_xp_deducted(self) -> None:
        """No XP is deducted when the Mage Scar gate blocks the transaction."""
        thread, xp_tracker = self._make_thread_with_xp(thread_level=10, xp_available=500)
        ThreadXPLockedLevelFactory(level=20, xp_cost=200)
        PendingAlterationFactory(character=thread.owner)

        with self.assertRaises(AlterationGateError):
            cross_thread_xp_lock(thread.owner, thread, 20)

        xp_tracker.refresh_from_db()
        self.assertEqual(xp_tracker.current_available, 500)

    def test_open_pending_alteration_no_unlock_row_created(self) -> None:
        """No ThreadLevelUnlock row is created when the Mage Scar gate blocks."""
        thread, _ = self._make_thread_with_xp(thread_level=10, xp_available=500)
        ThreadXPLockedLevelFactory(level=20, xp_cost=200)
        PendingAlterationFactory(character=thread.owner)

        with self.assertRaises(AlterationGateError):
            cross_thread_xp_lock(thread.owner, thread, 20)

        self.assertFalse(
            ThreadLevelUnlock.objects.filter(thread=thread, unlocked_level=20).exists()
        )

    def test_idempotent_unlock_bypasses_gate(self) -> None:
        """Already-unlocked boundary returns existing row without checking the gate."""
        from world.magic.factories import ThreadLevelUnlockFactory

        thread, _ = self._make_thread_with_xp(thread_level=10, xp_available=500)
        ThreadXPLockedLevelFactory(level=20, xp_cost=200)
        existing = ThreadLevelUnlockFactory(thread=thread, unlocked_level=20, xp_spent=200)
        # Add a Mage Scar AFTER the unlock already exists — idempotency path
        # must return existing without hitting the gate.
        PendingAlterationFactory(character=thread.owner)

        result = cross_thread_xp_lock(thread.owner, thread, 20)
        self.assertEqual(result.pk, existing.pk)


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
# compute_anchor_cap — FACET + COVENANT_ROLE arms (Spec D Task 25)
# =============================================================================


class ComputeAnchorCapFacetCovenantTests(TestCase):
    """Tests for FACET and COVENANT_ROLE arms of compute_anchor_cap."""

    def test_facet_cap_uses_lifetime_divided(self) -> None:
        """lifetime_earned=100, divisor=50 → cap = 2. Path stage defaults to 1, hard_max=20."""
        from world.magic.models import CharacterResonance, Thread
        from world.magic.services.threads import compute_anchor_cap

        sheet = CharacterSheetFactory(_path_stage=1)
        res = ResonanceFactory()
        facet = FacetFactory()
        thread = Thread.objects.create(
            owner=sheet,
            resonance=res,
            target_kind=TargetKind.FACET,
            target_facet=facet,
            name="Test Facet Thread",
        )
        CharacterResonance.objects.create(
            character_sheet=sheet, resonance=res, balance=0, lifetime_earned=100
        )
        # 100 // 50 = 2, hard_max = 1 * 20 = 20, so result = min(2, 20) = 2
        self.assertEqual(compute_anchor_cap(thread), 2)

    def test_facet_cap_capped_by_path_stage_x_20(self) -> None:
        """lifetime_earned=10000 would give 200 from division; path_stage=1 hard_max=20 wins."""
        from world.magic.models import CharacterResonance, Thread
        from world.magic.services.threads import compute_anchor_cap

        sheet = CharacterSheetFactory(_path_stage=1)
        res = ResonanceFactory()
        facet = FacetFactory()
        thread = Thread.objects.create(
            owner=sheet,
            resonance=res,
            target_kind=TargetKind.FACET,
            target_facet=facet,
            name="Test Facet Thread High",
        )
        CharacterResonance.objects.create(
            character_sheet=sheet, resonance=res, balance=0, lifetime_earned=10000
        )
        # 10000 // 50 = 200, hard_max = 1 * 20 = 20, so result = min(200, 20) = 20
        self.assertEqual(compute_anchor_cap(thread), 20)

    def test_covenant_role_cap_equals_covenant_level_x_10(self) -> None:
        """max(covenant.level) across CCR rows for this role × 10.

        Math: covenant.level=3 → cap = 3 * 10 = 30
        """
        from world.covenants.factories import (
            CharacterCovenantRoleFactory,
            CovenantFactory,
            CovenantRoleFactory,
        )
        from world.magic.models import Thread
        from world.magic.services.threads import compute_anchor_cap

        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        role = CovenantRoleFactory()
        cov = CovenantFactory(covenant_type=role.covenant_type, level=3)
        CharacterCovenantRoleFactory(character_sheet=sheet, covenant=cov, covenant_role=role)
        thread = Thread.objects.create(
            owner=sheet,
            resonance=res,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=role,
            name="Test Covenant Role Thread",
        )
        self.assertEqual(compute_anchor_cap(thread), 30)

    def test_item_and_room_kinds_dropped_from_target_kind(self) -> None:
        """ITEM and the superseded bare ROOM are both gone from TargetKind."""
        self.assertNotIn("ITEM", TargetKind.values)
        self.assertNotIn("ROOM", TargetKind.values)


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


# =============================================================================
# Gate 10.7 — Thread crossing threshold requirement gate (#1885)
# =============================================================================


class CrossingThresholdImbuingTests(TestCase):
    """spend_resonance_for_imbuing gates at PathStage crossing levels (3, 6, 11, 16, 21)
    when a ThreadCrossingThreshold exists with unmet requirements."""

    def setUp(self) -> None:
        from world.magic.services import spend_resonance_for_imbuing

        self.spend = spend_resonance_for_imbuing
        self.sheet = CharacterSheetFactory()
        self.resonance = ResonanceFactory()
        CharacterResonanceFactory(
            character_sheet=self.sheet, resonance=self.resonance, balance=9999
        )
        self.template = ItemTemplateFactory()

    def _make_thread_at_level(self, level: int) -> Thread:
        """Create a TRAIT thread at the given level with enough dp to advance.

        Sets a high trait value so the anchor cap doesn't block advancement.
        """
        return ThreadFactory(
            owner=self.sheet,
            resonance=self.resonance,
            level=level,
            developed_points=0,
            _trait_value=999,
        )

    def test_blocks_at_crossing_when_requirement_unmet(self) -> None:
        """Imbuing from level 2→3 blocks at the level-3 crossing when requirement unmet."""
        from world.magic.models import ThreadCrossingThreshold
        from world.progression.models import ItemRequirement

        threshold = ThreadCrossingThreshold.objects.create(target_kind=TargetKind.TRAIT, level=3)
        ItemRequirement.objects.create(
            thread_crossing_threshold=threshold,
            item_template=self.template,
            quantity=1,
        )
        thread = self._make_thread_at_level(2)
        result = self.spend(self.sheet, thread, 3)

        assert result.blocked_by == "CROSSING_REQUIREMENT"
        assert result.new_level == 2  # did NOT cross to 3
        assert result.levels_gained == 0
        assert len(result.blocked_requirement_messages) == 1
        assert "Need" in result.blocked_requirement_messages[0]

    def test_advances_through_crossing_when_requirement_met(self) -> None:
        """Imbuing from level 2→3 advances when the item requirement is satisfied."""
        from world.items.factories import ItemInstanceFactory
        from world.magic.models import ThreadCrossingThreshold
        from world.progression.models import ItemRequirement

        threshold = ThreadCrossingThreshold.objects.create(target_kind=TargetKind.TRAIT, level=3)
        ItemRequirement.objects.create(
            thread_crossing_threshold=threshold,
            item_template=self.template,
            quantity=1,
        )
        ItemInstanceFactory(template=self.template, holder_character_sheet=self.sheet)
        thread = self._make_thread_at_level(2)
        result = self.spend(self.sheet, thread, 1)

        assert result.blocked_by == "NONE"
        assert result.new_level == 3
        assert result.levels_gained == 1

    def test_fail_open_when_no_threshold_authored(self) -> None:
        """No ThreadCrossingThreshold row for (TRAIT, 3) → advance freely."""
        thread = self._make_thread_at_level(2)
        result = self.spend(self.sheet, thread, 1)

        assert result.blocked_by == "NONE"
        assert result.new_level == 3
        assert result.blocked_requirement_messages == []

    def test_fail_open_when_threshold_has_no_requirements(self) -> None:
        """Threshold exists but no requirements → fail-open (advance)."""
        from world.magic.models import ThreadCrossingThreshold

        ThreadCrossingThreshold.objects.create(target_kind=TargetKind.TRAIT, level=3)
        thread = self._make_thread_at_level(2)
        result = self.spend(self.sheet, thread, 1)

        assert result.blocked_by == "NONE"
        assert result.new_level == 3

    def test_partial_advance_below_crossing(self) -> None:
        """Resonance is spent and levels below the crossing are gained.

        From level 0 with amount=3: levels 0→1, 1→2 cost 1 dp each (2 dp),
        then the level-3 crossing blocks. Resonance is still deducted.
        """
        from world.magic.models import ThreadCrossingThreshold
        from world.progression.models import ItemRequirement

        threshold = ThreadCrossingThreshold.objects.create(target_kind=TargetKind.TRAIT, level=3)
        ItemRequirement.objects.create(
            thread_crossing_threshold=threshold,
            item_template=self.template,
            quantity=1,
        )
        thread = self._make_thread_at_level(0)
        result = self.spend(self.sheet, thread, 3)

        assert result.blocked_by == "CROSSING_REQUIREMENT"
        assert result.new_level == 2  # advanced 0→1→2, blocked at 3
        assert result.levels_gained == 2
        assert result.resonance_spent == 3

    def test_item_not_consumed_when_requirement_met(self) -> None:
        """The qualifying item is retained (possession-only, #1859 Decision 4)."""
        from world.items.factories import ItemInstanceFactory
        from world.items.models import ItemInstance
        from world.magic.models import ThreadCrossingThreshold
        from world.progression.models import ItemRequirement

        threshold = ThreadCrossingThreshold.objects.create(target_kind=TargetKind.TRAIT, level=3)
        ItemRequirement.objects.create(
            thread_crossing_threshold=threshold,
            item_template=self.template,
            quantity=1,
        )
        ItemInstanceFactory(template=self.template, holder_character_sheet=self.sheet)
        count_before = ItemInstance.objects.filter(
            holder_character_sheet=self.sheet, template=self.template
        ).count()

        thread = self._make_thread_at_level(2)
        self.spend(self.sheet, thread, 3)

        count_after = ItemInstance.objects.filter(
            holder_character_sheet=self.sheet, template=self.template
        ).count()
        assert count_before == count_after

    def test_blocks_at_level_6_crossing(self) -> None:
        """The gate fires at the level-6 crossing too."""
        from world.magic.models import ThreadCrossingThreshold
        from world.progression.models import ItemRequirement

        threshold = ThreadCrossingThreshold.objects.create(target_kind=TargetKind.TRAIT, level=6)
        ItemRequirement.objects.create(
            thread_crossing_threshold=threshold,
            item_template=self.template,
            quantity=1,
        )
        thread = self._make_thread_at_level(5)
        result = self.spend(self.sheet, thread, 1)

        assert result.blocked_by == "CROSSING_REQUIREMENT"
        assert result.new_level == 5

    def test_per_kind_scoping(self) -> None:
        """A TRAIT threshold at level 3 does not block a GIFT thread."""
        from world.magic.factories import GiftFactory
        from world.magic.models import ThreadCrossingThreshold
        from world.magic.specialization.services import provision_latent_gift_thread
        from world.progression.models import ItemRequirement

        threshold = ThreadCrossingThreshold.objects.create(target_kind=TargetKind.TRAIT, level=3)
        ItemRequirement.objects.create(
            thread_crossing_threshold=threshold,
            item_template=self.template,
            quantity=1,
        )
        # A GIFT thread at level 2 should NOT be gated by a TRAIT threshold
        gift = GiftFactory()
        provision_latent_gift_thread(self.sheet, gift, resonance=self.resonance)
        thread = next(
            t for t in self.sheet.character.threads.all() if t.target_kind == TargetKind.GIFT
        )
        thread.level = 2
        thread.save(update_fields=["level"])
        result = self.spend(self.sheet, thread, 1)
        assert result.blocked_by == "NONE"
        assert result.new_level == 3
