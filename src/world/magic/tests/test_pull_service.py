"""Tests for spend_resonance_for_pull (Spec A §3.8 + §5.4 + §7.4)."""

from __future__ import annotations

from django.db import IntegrityError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
)
from world.combat.models import CombatPull
from world.magic.constants import EffectKind, TargetKind, VitalBonusTarget
from world.magic.exceptions import (
    InvalidImbueAmount,
    ResonanceInsufficient,
)
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterResonanceFactory,
    ResonanceFactory,
    ThreadFactory,
    ThreadPullCostFactory,
    ThreadPullEffectFactory,
)
from world.magic.models import CharacterAnima, CharacterResonance
from world.magic.services import _anchor_in_action, spend_resonance_for_pull
from world.magic.types import PullActionContext


def _setup_combat_context(
    *,
    sheet,
    encounter_round: int = 1,
) -> PullActionContext:
    encounter = CombatEncounterFactory(round_number=encounter_round)
    participant = CombatParticipantFactory(
        encounter=encounter,
        character_sheet=sheet,
    )
    return PullActionContext(
        combat_encounter=encounter,
        participant=participant,
    )


class SpendResonanceForPullCombatTests(TestCase):
    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        CharacterAnimaFactory(character=self.sheet.character, current=10, maximum=10)
        self.resonance = ResonanceFactory()
        CharacterResonanceFactory(
            character_sheet=self.sheet,
            resonance=self.resonance,
            balance=10,
            lifetime_earned=10,
        )
        self.cost = ThreadPullCostFactory(
            tier=1,
            resonance_cost=2,
            anima_per_thread=1,
        )

    def _make_thread(self):
        thread = ThreadFactory(owner=self.sheet, resonance=self.resonance)
        # Authored tier-1 FLAT_BONUS row matching the thread's anchor kind.
        ThreadPullEffectFactory(
            target_kind=thread.target_kind,
            resonance=self.resonance,
            tier=1,
            flat_bonus_amount=3,
        )
        return thread

    def test_combat_context_writes_combat_pull_row(self) -> None:
        thread = self._make_thread()
        ctx = _setup_combat_context(sheet=self.sheet)
        ctx = PullActionContext(
            combat_encounter=ctx.combat_encounter,
            participant=ctx.participant,
            involved_traits=(thread.target_trait_id,),
        )

        pre = CombatPull.objects.count()
        result = spend_resonance_for_pull(
            self.sheet,
            self.resonance,
            tier=1,
            threads=[thread],
            action_context=ctx,
        )

        self.assertEqual(CombatPull.objects.count() - pre, 1)
        self.assertEqual(result.resonance_spent, 2)
        # Single thread → max(0, 1-1) × anima_per_thread = 0.
        self.assertEqual(result.anima_spent, 0)
        # tier 0 + tier 1 effects authored; tier-0 default is FLAT_BONUS=1.
        self.assertGreaterEqual(len(result.resolved_effects), 1)

    def test_balance_and_anima_debited(self) -> None:
        thread = self._make_thread()
        thread2 = ThreadFactory(owner=self.sheet, resonance=self.resonance)
        ctx = _setup_combat_context(sheet=self.sheet)
        ctx = PullActionContext(
            combat_encounter=ctx.combat_encounter,
            participant=ctx.participant,
            involved_traits=(thread.target_trait_id, thread2.target_trait_id),
        )

        spend_resonance_for_pull(
            self.sheet,
            self.resonance,
            tier=1,
            threads=[thread, thread2],
            action_context=ctx,
        )

        cr = self.sheet.character.resonances.get_or_create(self.resonance)
        cr.refresh_from_db()
        self.assertEqual(cr.balance, 8)  # 10 − 2
        # Two threads → max(0, 2−1) × 1 = 1 anima.
        anima = CharacterAnima.objects.get(character=self.sheet.character)
        self.assertEqual(anima.current, 9)

    def test_double_commit_same_round_rejected(self) -> None:
        thread = self._make_thread()
        ctx = _setup_combat_context(sheet=self.sheet)
        ctx = PullActionContext(
            combat_encounter=ctx.combat_encounter,
            participant=ctx.participant,
            involved_traits=(thread.target_trait_id,),
        )

        spend_resonance_for_pull(
            self.sheet,
            self.resonance,
            tier=1,
            threads=[thread],
            action_context=ctx,
        )
        with self.assertRaises(IntegrityError):
            spend_resonance_for_pull(
                self.sheet,
                self.resonance,
                tier=1,
                threads=[thread],
                action_context=ctx,
            )
        # The second call's unique-key violation fires inside
        # _persist_combat_pull, BEFORE the balance debit runs. So no
        # second debit should have hit the DB — balance must stay at 8.
        cr = CharacterResonance.objects.get(
            character_sheet=self.sheet,
            resonance=self.resonance,
        )
        cr.refresh_from_db()
        self.assertEqual(cr.balance, 8)

    def test_anchor_not_in_action_rejected(self) -> None:
        thread = self._make_thread()
        ctx = _setup_combat_context(sheet=self.sheet)
        # Note: involved_traits is empty — the thread's trait is NOT in scope.
        with self.assertRaises(InvalidImbueAmount):
            spend_resonance_for_pull(
                self.sheet,
                self.resonance,
                tier=1,
                threads=[thread],
                action_context=ctx,
            )

    def test_relationship_anchor_always_in_action(self) -> None:
        # Relationship-track threads bypass the involvement check entirely.
        thread = ThreadFactory(
            owner=self.sheet,
            resonance=self.resonance,
            as_track_thread=True,
        )
        ctx = _setup_combat_context(sheet=self.sheet)

        pre = CombatPull.objects.count()
        spend_resonance_for_pull(
            self.sheet,
            self.resonance,
            tier=1,
            threads=[thread],
            action_context=ctx,
        )
        self.assertEqual(CombatPull.objects.count() - pre, 1)

    def test_thread_not_owned_rejected(self) -> None:
        other_sheet = CharacterSheetFactory()
        thread = ThreadFactory(owner=other_sheet, resonance=self.resonance)
        ctx = _setup_combat_context(sheet=self.sheet)
        ctx = PullActionContext(
            combat_encounter=ctx.combat_encounter,
            participant=ctx.participant,
            involved_traits=(thread.target_trait_id,),
        )
        with self.assertRaises(InvalidImbueAmount):
            spend_resonance_for_pull(
                self.sheet,
                self.resonance,
                tier=1,
                threads=[thread],
                action_context=ctx,
            )

    def test_resonance_mismatch_rejected(self) -> None:
        other_resonance = ResonanceFactory()
        thread = ThreadFactory(owner=self.sheet, resonance=other_resonance)
        ctx = _setup_combat_context(sheet=self.sheet)
        ctx = PullActionContext(
            combat_encounter=ctx.combat_encounter,
            participant=ctx.participant,
            involved_traits=(thread.target_trait_id,),
        )
        with self.assertRaises(InvalidImbueAmount):
            spend_resonance_for_pull(
                self.sheet,
                self.resonance,
                tier=1,
                threads=[thread],
                action_context=ctx,
            )

    def test_empty_threads_rejected(self) -> None:
        ctx = _setup_combat_context(sheet=self.sheet)
        with self.assertRaises(InvalidImbueAmount):
            spend_resonance_for_pull(
                self.sheet,
                self.resonance,
                tier=1,
                threads=[],
                action_context=ctx,
            )

    def test_insufficient_balance_rejected(self) -> None:
        # Drain balance below cost.
        cr = self.sheet.character.resonances.get_or_create(self.resonance)
        cr.balance = 1
        cr.save(update_fields=["balance"])
        thread = self._make_thread()
        ctx = _setup_combat_context(sheet=self.sheet)
        ctx = PullActionContext(
            combat_encounter=ctx.combat_encounter,
            participant=ctx.participant,
            involved_traits=(thread.target_trait_id,),
        )
        with self.assertRaises(ResonanceInsufficient):
            spend_resonance_for_pull(
                self.sheet,
                self.resonance,
                tier=1,
                threads=[thread],
                action_context=ctx,
            )

    def test_insufficient_anima_rejected_for_multi_thread(self) -> None:
        # Make anima 0 so multi-thread pull (which needs anima_per_thread × (n-1))
        # fails even though balance is fine.
        anima = CharacterAnima.objects.get(character=self.sheet.character)
        anima.current = 0
        anima.save(update_fields=["current"])

        t1 = self._make_thread()
        t2 = ThreadFactory(owner=self.sheet, resonance=self.resonance)
        ctx = _setup_combat_context(sheet=self.sheet)
        ctx = PullActionContext(
            combat_encounter=ctx.combat_encounter,
            participant=ctx.participant,
            involved_traits=(t1.target_trait_id, t2.target_trait_id),
        )
        with self.assertRaises(ResonanceInsufficient):
            spend_resonance_for_pull(
                self.sheet,
                self.resonance,
                tier=1,
                threads=[t1, t2],
                action_context=ctx,
            )

    def test_level_scaling_uses_thread_level(self) -> None:
        # Thread at level 20 → multiplier = max(1, 20//10) = 2.
        thread = ThreadFactory(
            owner=self.sheet,
            resonance=self.resonance,
            level=20,
        )
        ThreadPullEffectFactory(
            target_kind=thread.target_kind,
            resonance=self.resonance,
            tier=1,
            flat_bonus_amount=5,
        )
        ctx = _setup_combat_context(sheet=self.sheet)
        ctx = PullActionContext(
            combat_encounter=ctx.combat_encounter,
            participant=ctx.participant,
            involved_traits=(thread.target_trait_id,),
        )

        result = spend_resonance_for_pull(
            self.sheet,
            self.resonance,
            tier=1,
            threads=[thread],
            action_context=ctx,
        )

        flat_rows = [
            r
            for r in result.resolved_effects
            if r.kind == EffectKind.FLAT_BONUS and r.source_tier == 1
        ]
        self.assertEqual(len(flat_rows), 1)
        self.assertEqual(flat_rows[0].scaled_value, 10)
        self.assertEqual(flat_rows[0].level_multiplier, 2)


class SpendResonanceForPullEphemeralTests(TestCase):
    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        CharacterAnimaFactory(character=self.sheet.character, current=10, maximum=10)
        self.resonance = ResonanceFactory()
        CharacterResonanceFactory(
            character_sheet=self.sheet,
            resonance=self.resonance,
            balance=10,
            lifetime_earned=10,
        )
        ThreadPullCostFactory(tier=1, resonance_cost=2, anima_per_thread=1)
        # Bump thread to level 1 so both authored effect rows (min_level 0/1) apply.
        self.thread = ThreadFactory(
            owner=self.sheet,
            resonance=self.resonance,
            level=1,
        )
        ThreadPullEffectFactory(
            target_kind=self.thread.target_kind,
            resonance=self.resonance,
            tier=1,
            min_thread_level=0,
            flat_bonus_amount=3,
        )
        # Wire a tier-1 VITAL_BONUS row at min_level=1 so the (kind,res,tier,level)
        # unique key differs from the FLAT_BONUS row above. Both apply to the
        # level-1 thread per the min_thread_level__lte filter.
        ThreadPullEffectFactory(
            target_kind=self.thread.target_kind,
            resonance=self.resonance,
            tier=1,
            min_thread_level=1,
            as_vital_bonus=True,
            vital_bonus_amount=4,
            vital_target=VitalBonusTarget.MAX_HEALTH,
            flat_bonus_amount=None,
        )
        self.ctx = PullActionContext(
            combat_encounter=None,
            participant=None,
            involved_traits=(self.thread.target_trait_id,),
        )

    def test_ephemeral_writes_zero_combat_pulls(self) -> None:
        pre = CombatPull.objects.count()
        result = spend_resonance_for_pull(
            self.sheet,
            self.resonance,
            tier=1,
            threads=[self.thread],
            action_context=self.ctx,
        )
        self.assertEqual(CombatPull.objects.count() - pre, 0)
        self.assertGreater(result.resonance_spent, 0)

    def test_ephemeral_still_debits_resonance(self) -> None:
        spend_resonance_for_pull(
            self.sheet,
            self.resonance,
            tier=1,
            threads=[self.thread],
            action_context=self.ctx,
        )
        cr = self.sheet.character.resonances.get_or_create(self.resonance)
        cr.refresh_from_db()
        self.assertEqual(cr.balance, 8)

    def test_ephemeral_marks_vital_bonus_inactive(self) -> None:
        result = spend_resonance_for_pull(
            self.sheet,
            self.resonance,
            tier=1,
            threads=[self.thread],
            action_context=self.ctx,
        )
        vital_rows = [r for r in result.resolved_effects if r.kind == EffectKind.VITAL_BONUS]
        self.assertEqual(len(vital_rows), 1)
        self.assertTrue(vital_rows[0].inactive)
        self.assertEqual(vital_rows[0].scaled_value, 0)
        self.assertIsNotNone(vital_rows[0].inactive_reason)

    def test_ephemeral_flat_bonus_still_active(self) -> None:
        # FLAT_BONUS is unaffected by ephemeral context — only VITAL_BONUS goes
        # inactive (no max-health / damage-reduction consumer outside combat).
        result = spend_resonance_for_pull(
            self.sheet,
            self.resonance,
            tier=1,
            threads=[self.thread],
            action_context=self.ctx,
        )
        flat_rows = [r for r in result.resolved_effects if r.kind == EffectKind.FLAT_BONUS]
        self.assertTrue(any(not r.inactive and r.scaled_value > 0 for r in flat_rows))


class AnchorInActionTests(TestCase):
    """Direct coverage of `_anchor_in_action`'s typed-FK matching."""

    def test_relationship_track_always_in_action(self) -> None:
        sheet = CharacterSheetFactory()
        thread = ThreadFactory(owner=sheet, as_track_thread=True)
        ctx = PullActionContext(combat_encounter=None, participant=None)
        self.assertTrue(_anchor_in_action(thread, ctx))

    def test_capstone_always_in_action(self) -> None:
        sheet = CharacterSheetFactory()
        thread = ThreadFactory(owner=sheet, as_capstone_thread=True)
        ctx = PullActionContext(combat_encounter=None, participant=None)
        self.assertTrue(_anchor_in_action(thread, ctx))

    def test_trait_matched_by_involved_traits(self) -> None:
        sheet = CharacterSheetFactory()
        thread = ThreadFactory(owner=sheet)
        self.assertEqual(thread.target_kind, TargetKind.TRAIT)
        ctx_in = PullActionContext(involved_traits=(thread.target_trait_id,))
        ctx_out = PullActionContext(involved_traits=(99999,))
        self.assertTrue(_anchor_in_action(thread, ctx_in))
        self.assertFalse(_anchor_in_action(thread, ctx_out))

    def test_technique_matched_by_involved_techniques(self) -> None:
        sheet = CharacterSheetFactory()
        thread = ThreadFactory(owner=sheet, as_technique_thread=True)
        ctx_in = PullActionContext(involved_techniques=(thread.target_technique_id,))
        ctx_out = PullActionContext(involved_techniques=())
        self.assertTrue(_anchor_in_action(thread, ctx_in))
        self.assertFalse(_anchor_in_action(thread, ctx_out))
