"""Tests for Phase 13 VITAL_BONUS routing (Spec A §3.8 + §5.5 + §5.8 + §7.4).

Covers three responsibilities of the routing layer:

- ``recompute_max_health_with_threads`` folds passive tier-0 + active-pull
  tier 1+ VITAL_BONUS MAX_HEALTH contributions into ``vitals.max_health``.
- ``recompute_max_health`` enforces clamp-not-injure: shrinking the max
  never pushes current_health below the level it already sat at.
- ``apply_damage_reduction_from_threads`` subtracts the DAMAGE_TAKEN_REDUCTION
  sum (passive + pulled) from an incoming-damage value, never going below 0.
"""

from __future__ import annotations

from django.db import connection
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
    CombatPullFactory,
    CombatPullResolvedEffectFactory,
)
from world.magic.constants import EffectKind, VitalBonusTarget
from world.magic.factories import (
    ResonanceFactory,
    ThreadFactory,
    ThreadPullEffectFactory,
)
from world.magic.models import Thread
from world.magic.services import (
    apply_damage_reduction_from_threads,
    recompute_max_health_with_threads,
)
from world.vitals.models import CharacterVitals
from world.vitals.services import recompute_max_health


class MaxHealthVitalBonusTests(TestCase):
    """Passive + pulled MAX_HEALTH contributions feed recompute_max_health."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.vitals = CharacterVitals.objects.create(
            character_sheet=self.sheet,
            health=80,
            max_health=100,
            base_max_health=100,
        )

    def test_no_threads_max_unchanged(self) -> None:
        """No threads, no pulls → max = base_max_health."""
        recompute_max_health_with_threads(self.sheet)
        self.vitals.refresh_from_db()
        self.assertEqual(self.vitals.max_health, 100)

    def test_passive_tier0_max_health_increases_max(self) -> None:
        """A tier-0 VITAL_BONUS MAX_HEALTH row on a level-20 thread adds (20//10)*amount."""
        resonance = ResonanceFactory()
        thread = ThreadFactory(owner=self.sheet, resonance=resonance, level=20)
        ThreadPullEffectFactory(
            target_kind=thread.target_kind,
            resonance=resonance,
            tier=0,
            min_thread_level=0,
            effect_kind=EffectKind.VITAL_BONUS,
            flat_bonus_amount=None,
            vital_bonus_amount=5,
            vital_target=VitalBonusTarget.MAX_HEALTH,
        )

        recompute_max_health_with_threads(self.sheet)
        self.vitals.refresh_from_db()
        # base=100, level=20 → multiplier max(1, 20//10)=2, 5×2=10 addend.
        self.assertEqual(self.vitals.max_health, 110)

    def test_active_pull_tier1_max_health_increases_max(self) -> None:
        """A CombatPull with a tier-1 MAX_HEALTH resolved effect adds scaled_value."""
        encounter = CombatEncounterFactory(round_number=1)
        participant = CombatParticipantFactory(
            encounter=encounter,
            character_sheet=self.sheet,
        )
        pull = CombatPullFactory(
            participant=participant,
            encounter=encounter,
            round_number=1,
        )
        CombatPullResolvedEffectFactory(
            pull=pull,
            kind=EffectKind.VITAL_BONUS,
            authored_value=8,
            level_multiplier=2,
            scaled_value=16,
            vital_target=VitalBonusTarget.MAX_HEALTH,
        )

        recompute_max_health_with_threads(self.sheet)
        self.vitals.refresh_from_db()
        self.assertEqual(self.vitals.max_health, 116)

    def test_passive_plus_pull_stack(self) -> None:
        """Passive and active-pull contributions stack additively."""
        resonance = ResonanceFactory()
        thread = ThreadFactory(owner=self.sheet, resonance=resonance, level=20)
        ThreadPullEffectFactory(
            target_kind=thread.target_kind,
            resonance=resonance,
            tier=0,
            min_thread_level=0,
            effect_kind=EffectKind.VITAL_BONUS,
            flat_bonus_amount=None,
            vital_bonus_amount=5,
            vital_target=VitalBonusTarget.MAX_HEALTH,
        )
        encounter = CombatEncounterFactory(round_number=1)
        participant = CombatParticipantFactory(
            encounter=encounter,
            character_sheet=self.sheet,
        )
        pull = CombatPullFactory(
            participant=participant,
            encounter=encounter,
            round_number=1,
        )
        CombatPullResolvedEffectFactory(
            pull=pull,
            kind=EffectKind.VITAL_BONUS,
            authored_value=3,
            level_multiplier=2,
            scaled_value=6,
            vital_target=VitalBonusTarget.MAX_HEALTH,
        )

        recompute_max_health_with_threads(self.sheet)
        self.vitals.refresh_from_db()
        # passive 10 + pulled 6 = 16.
        self.assertEqual(self.vitals.max_health, 116)


class ClampNotInjureTests(TestCase):
    """Shrinking max_health never pushes current_health below its prior level."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()

    def test_current_untouched_when_new_max_above_current(self) -> None:
        """new_max (100) >= current (80) → current stays at 80."""
        vitals = CharacterVitals.objects.create(
            character_sheet=self.sheet,
            health=80,
            max_health=120,
            base_max_health=100,
        )
        recompute_max_health(self.sheet, thread_addend=0)
        vitals.refresh_from_db()
        self.assertEqual(vitals.max_health, 100)
        self.assertEqual(vitals.health, 80)

    def test_current_clamped_down_when_new_max_below_current(self) -> None:
        """new_max (100) < current (120) → current clamped to 100."""
        vitals = CharacterVitals.objects.create(
            character_sheet=self.sheet,
            health=120,
            max_health=120,
            base_max_health=100,
        )
        recompute_max_health(self.sheet, thread_addend=0)
        vitals.refresh_from_db()
        self.assertEqual(vitals.max_health, 100)
        self.assertEqual(vitals.health, 100)

    def test_pull_expiry_does_not_lower_current_below_existing(self) -> None:
        """Bolstered character takes damage, pull expires: current stays.

        Scenario (Spec A §3.8 lines 1057-1078):
          - base_max_health=100, pull adds +20 → max=120
          - character takes 25 damage → current=95 (under original 100, fine)
          - pull expires, addend drops to 0 → max recomputes to 100
          - expected: current stays 95 (NOT pushed down to 70)
        """
        vitals = CharacterVitals.objects.create(
            character_sheet=self.sheet,
            health=95,  # took 25 damage from bolstered 120.
            max_health=120,
            base_max_health=100,
        )
        # Addend=0 simulates the post-expiry state.
        recompute_max_health(self.sheet, thread_addend=0)
        vitals.refresh_from_db()
        self.assertEqual(vitals.max_health, 100)
        self.assertEqual(vitals.health, 95)

    def test_pull_expiry_clamps_overflow_current_to_new_max(self) -> None:
        """Fully-healthy bolstered character: pull expiry clamps to new max.

        Scenario:
          - base=100, pull +20 → max=120, current=120 (full health)
          - pull expires, addend=0 → max=100
          - current clamped down to new max (100), not kept at 120.
        """
        vitals = CharacterVitals.objects.create(
            character_sheet=self.sheet,
            health=120,
            max_health=120,
            base_max_health=100,
        )
        recompute_max_health(self.sheet, thread_addend=0)
        vitals.refresh_from_db()
        self.assertEqual(vitals.max_health, 100)
        self.assertEqual(vitals.health, 100)


class DamageReductionRoutingTests(TestCase):
    """apply_damage_reduction_from_threads subtracts passive + pulled DR."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        CharacterVitals.objects.create(
            character_sheet=self.sheet,
            health=100,
            max_health=100,
            base_max_health=100,
        )

    def test_no_threads_damage_unchanged(self) -> None:
        self.assertEqual(
            apply_damage_reduction_from_threads(self.sheet.character, 30),
            30,
        )

    def test_passive_dr_reduces_incoming_damage(self) -> None:
        """Tier-0 DAMAGE_TAKEN_REDUCTION row on a level-10 thread subtracts scaled value."""
        resonance = ResonanceFactory()
        thread = ThreadFactory(owner=self.sheet, resonance=resonance, level=10)
        ThreadPullEffectFactory(
            target_kind=thread.target_kind,
            resonance=resonance,
            tier=0,
            min_thread_level=0,
            effect_kind=EffectKind.VITAL_BONUS,
            flat_bonus_amount=None,
            vital_bonus_amount=3,
            vital_target=VitalBonusTarget.DAMAGE_TAKEN_REDUCTION,
        )

        # level=10 → multiplier max(1, 10//10)=1, 3×1=3 subtracted from 30.
        self.assertEqual(
            apply_damage_reduction_from_threads(self.sheet.character, 30),
            27,
        )

    def test_active_pull_dr_reduces_incoming_damage(self) -> None:
        encounter = CombatEncounterFactory(round_number=1)
        participant = CombatParticipantFactory(
            encounter=encounter,
            character_sheet=self.sheet,
        )
        pull = CombatPullFactory(
            participant=participant,
            encounter=encounter,
            round_number=1,
        )
        CombatPullResolvedEffectFactory(
            pull=pull,
            kind=EffectKind.VITAL_BONUS,
            authored_value=5,
            level_multiplier=2,
            scaled_value=10,
            vital_target=VitalBonusTarget.DAMAGE_TAKEN_REDUCTION,
        )

        self.assertEqual(
            apply_damage_reduction_from_threads(self.sheet.character, 30),
            20,
        )

    def test_dr_never_returns_negative_damage(self) -> None:
        """Even when DR exceeds damage, result floors at 0."""
        resonance = ResonanceFactory()
        thread = ThreadFactory(owner=self.sheet, resonance=resonance, level=20)
        ThreadPullEffectFactory(
            target_kind=thread.target_kind,
            resonance=resonance,
            tier=0,
            min_thread_level=0,
            effect_kind=EffectKind.VITAL_BONUS,
            flat_bonus_amount=None,
            vital_bonus_amount=50,
            vital_target=VitalBonusTarget.DAMAGE_TAKEN_REDUCTION,
        )

        # DR total = 50 × 2 = 100, incoming = 5 → max(0, 5-100) = 0.
        self.assertEqual(
            apply_damage_reduction_from_threads(self.sheet.character, 5),
            0,
        )

    def test_dr_only_matches_damage_taken_reduction_target(self) -> None:
        """MAX_HEALTH rows must NOT be picked up by the DR path."""
        resonance = ResonanceFactory()
        thread = ThreadFactory(owner=self.sheet, resonance=resonance, level=20)
        # A MAX_HEALTH bonus that should NOT reduce incoming damage.
        ThreadPullEffectFactory(
            target_kind=thread.target_kind,
            resonance=resonance,
            tier=0,
            min_thread_level=0,
            effect_kind=EffectKind.VITAL_BONUS,
            flat_bonus_amount=None,
            vital_bonus_amount=10,
            vital_target=VitalBonusTarget.MAX_HEALTH,
        )

        self.assertEqual(
            apply_damage_reduction_from_threads(self.sheet.character, 20),
            20,
        )


class AnchorInScopeVacuousTests(TestCase):
    """Anchor-in-scope filter is vacuous because all Thread typed FKs use PROTECT.

    Spec §5.8 lines 1650-1652 requires passive contributions only from threads
    "whose anchor is currently in scope." All Thread typed FKs (target_trait,
    target_technique, target_object, target_relationship_track, target_capstone)
    use on_delete=PROTECT, so deleting any anchor object raises ProtectedError
    rather than silently removing or nulling the FK. An existing Thread row
    therefore always has its anchor present.

    These tests confirm:
    1. Deleting a trait anchor object raises ProtectedError (proving PROTECT).
    2. passive_vital_bonuses still returns the correct total when multiple
       threads exist across different (target_kind, resonance_id) pairs — the
       single-query rewrite handles them all correctly.
    """

    def test_deleting_trait_anchor_raises_protected_error(self) -> None:
        """Deleting the target Trait raises ProtectedError — anchor cannot vanish."""
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        thread = ThreadFactory(owner=sheet, resonance=resonance, level=10)
        trait = thread.target_trait

        with self.assertRaises(ProtectedError):
            trait.delete()

        # Thread still exists; anchor was never deleted.
        self.assertTrue(Thread.objects.filter(pk=thread.pk).exists())

    def test_passive_vital_bonuses_single_query_multi_thread(self) -> None:
        """passive_vital_bonuses fires ONE query regardless of thread count.

        Three threads on different resonances all have a tier-0 MAX_HEALTH
        row; the method should batch them in a single DB round-trip and
        return the correct summed total.
        """
        sheet = CharacterSheetFactory()
        CharacterVitals.objects.create(
            character_sheet=sheet,
            health=100,
            max_health=100,
            base_max_health=100,
        )

        # Three threads, each with a tier-0 MAX_HEALTH +5 effect.
        for _ in range(3):
            resonance = ResonanceFactory()
            thread = ThreadFactory(owner=sheet, resonance=resonance, level=10)
            ThreadPullEffectFactory(
                target_kind=thread.target_kind,
                resonance=resonance,
                tier=0,
                min_thread_level=0,
                effect_kind=EffectKind.VITAL_BONUS,
                flat_bonus_amount=None,
                vital_bonus_amount=5,
                vital_target=VitalBonusTarget.MAX_HEALTH,
            )

        # Warm the _all cache (simulates what recompute_max_health_with_threads
        # does via character.threads._all).
        handler = sheet.character.threads
        _ = handler._all  # prime cache

        with CaptureQueriesContext(connection) as ctx:
            total = handler.passive_vital_bonuses(VitalBonusTarget.MAX_HEALTH)

        # level=10 → multiplier max(1,10//10)=1; 5×1×3 threads = 15.
        self.assertEqual(total, 15)
        # Exactly one query for all ThreadPullEffect rows.
        self.assertEqual(
            len(ctx.captured_queries),
            1,
            msg=f"Expected 1 query, got {len(ctx.captured_queries)}: "
            f"{[q['sql'] for q in ctx.captured_queries]}",
        )
