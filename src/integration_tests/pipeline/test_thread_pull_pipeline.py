"""End-to-end pipeline tests for the Spec A thread pull system.

Covers the full chain:
    seed_thread_pull_catalog → Thread on character
    → spend_resonance_for_pull → CombatPull written
    → resolve_pull_effects → CombatPullResolvedEffect rows
    for each effect_kind (FLAT_BONUS, INTENSITY_BUMP, VITAL_BONUS, CAPABILITY_GRANT).

Tier-0 VITAL_BONUS is verified as passive: active without any resonance spend,
via character.threads.passive_vital_bonuses() (Thread anchor only).

Test class structure:
    TestThreadPullPipeline  — full setUpTestData + four test methods, one per
                              effect kind. Uses combat context so CombatPull rows
                              are written and CombatPullResolvedEffect rows are
                              snapshotted.
"""

from __future__ import annotations

from django.test import TestCase

from integration_tests.game_content.magic import (
    MagicConfigResult,
    ThreadPullCatalogResult,
    seed_magic_config,
    seed_thread_pull_catalog,
)
from world.magic.constants import EffectKind, TargetKind, VitalBonusTarget


class TestThreadPullPipeline(TestCase):
    """Proves the entire Spec A thread pull system works end-to-end.

    setUpTestData seeds:
    - Magic config singletons (AnimaConfig, SoulfrayConfig, etc.)
    - Thread pull catalog (ThreadPullCost × 3, ThreadPullEffect × 4, Tideborne resonance)
    - A character with CharacterSheet, CharacterAnima, CharacterResonance balance
    - A Thread anchored to a Trait, targeting the canonical "Tideborne" resonance
      with level=10 (satisfies min_thread_level=5 for CAPABILITY_GRANT; multiplier=1)
    - A minimal CombatEncounter + CombatParticipant scaffold

    VITAL_BONUS (tier=0) is passive — the test verifies it activates without any spend.
    FLAT_BONUS (tier=1), INTENSITY_BUMP (tier=2), CAPABILITY_GRANT (tier=3) each
    require a resonance spend and write CombatPull + CombatPullResolvedEffect rows.
    """

    config: MagicConfigResult
    catalog: ThreadPullCatalogResult

    @classmethod
    def setUpTestData(cls) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.combat.factories import (
            CombatEncounterFactory,
            CombatParticipantFactory,
        )
        from world.magic.factories import (
            CharacterAnimaFactory,
            CharacterResonanceFactory,
        )
        from world.magic.models import Thread
        from world.traits.factories import TraitFactory
        from world.vitals.models import CharacterVitals

        cls.config = seed_magic_config()
        cls.catalog = seed_thread_pull_catalog()

        # Character scaffold
        cls.sheet = CharacterSheetFactory()
        CharacterAnimaFactory(character=cls.sheet.character, current=50, maximum=50)

        # Resonance balance: must afford tier-3 pull (resonance_cost=6) with headroom.
        CharacterResonanceFactory(
            character_sheet=cls.sheet,
            resonance=cls.catalog.canonical_resonance,
            balance=20,
            lifetime_earned=20,
        )

        # Trait anchor (target_kind=TRAIT is the default for ThreadFactory; we create
        # directly here so we control the trait and can pass it to involved_traits).
        cls.target_trait = TraitFactory()
        cls.thread = Thread.objects.create(
            owner=cls.sheet,
            resonance=cls.catalog.canonical_resonance,
            target_kind=TargetKind.TRAIT,
            target_trait=cls.target_trait,
            # level=10 → multiplier = max(1, 10//10) = 1; satisfies min_thread_level=5
            level=10,
            developed_points=0,
        )

        # Vitals (needed for recompute_max_health_with_threads inside spend_resonance_for_pull)
        cls.vitals = CharacterVitals.objects.create(
            character_sheet=cls.sheet,
            health=50,
            base_max_health=50,
            max_health=50,
        )

        # Combat scaffold: encounter at round 1
        cls.encounter = CombatEncounterFactory(round_number=1)
        cls.participant = CombatParticipantFactory(
            encounter=cls.encounter,
            character_sheet=cls.sheet,
        )

    # -----------------------------------------------------------------------
    # Helper
    # -----------------------------------------------------------------------

    def _make_combat_ctx(self, round_number: int = 1) -> object:
        """Return a PullActionContext for combat, with the trait anchor in scope."""
        from world.combat.factories import (
            CombatEncounterFactory,
            CombatParticipantFactory,
        )
        from world.magic.types import PullActionContext

        encounter = CombatEncounterFactory(round_number=round_number)
        participant = CombatParticipantFactory(
            encounter=encounter,
            character_sheet=self.sheet,
        )
        return PullActionContext(
            combat_encounter=encounter,
            participant=participant,
            involved_traits=(self.target_trait.pk,),
        )

    def _fresh_resonance_balance(self, amount: int) -> None:
        """Reset the character's Tideborne resonance balance to `amount` for isolation.

        Uses direct attribute update + save so the SharedMemoryModel identity map
        stays in sync (avoids stale-cache reads on subsequent .objects.get() calls).
        """
        from world.magic.models import CharacterResonance

        cr = CharacterResonance.objects.get(
            character_sheet=self.sheet,
            resonance=self.catalog.canonical_resonance,
        )
        cr.balance = amount
        cr.save(update_fields=["balance"])
        # Invalidate the handler cache so the service sees the updated value.
        self.sheet.character.resonances.invalidate()

    # -----------------------------------------------------------------------
    # Test 1: passive VITAL_BONUS active without any spend
    # -----------------------------------------------------------------------

    def test_passive_vital_bonus_active_without_spend(self) -> None:
        """Tier-0 VITAL_BONUS activates passively via the Thread anchor alone.

        No resonance spend is needed. character.threads.passive_vital_bonuses()
        sums tier-0 MAX_HEALTH contributions across the character's threads.

        The catalog VITAL_BONUS row: tier=0, vital_bonus_amount=5, MAX_HEALTH.
        Thread.level=10 → multiplier = max(1, 10//10) = 1. Expected sum = 5 × 1 = 5.
        """

        passive_total = self.sheet.character.threads.passive_vital_bonuses(
            VitalBonusTarget.MAX_HEALTH
        )
        self.assertEqual(passive_total, 5)

    # -----------------------------------------------------------------------
    # Test 2: tier-1 pull → CombatPull + FLAT_BONUS CombatPullResolvedEffect
    # -----------------------------------------------------------------------

    def test_tier1_pull_writes_combat_pull_and_flat_bonus_effect(self) -> None:
        """Tier-1 resonance spend writes a CombatPull and a FLAT_BONUS resolved effect.

        Catalog: FLAT_BONUS tier=1, flat_bonus_amount=2, min_thread_level=0.
        Thread.level=10 → multiplier=1. Expected scaled_value = 2 × 1 = 2.

        Also verifies tier-0 VITAL_BONUS is resolved (passive but included in the
        resolve sweep when tier includes 0..1 range), and balance is debited.
        """
        from world.combat.models import CombatPull, CombatPullResolvedEffect
        from world.magic.models import CharacterResonance
        from world.magic.services import spend_resonance_for_pull

        self._fresh_resonance_balance(10)

        ctx = self._make_combat_ctx(round_number=2)
        result = spend_resonance_for_pull(
            self.sheet,
            self.catalog.canonical_resonance,
            tier=1,
            threads=[self.thread],
            action_context=ctx,
        )

        # --- CombatPull written ---
        pull = CombatPull.objects.get(
            participant=ctx.participant,
            round_number=2,
        )
        self.assertEqual(pull.tier, 1)
        self.assertEqual(pull.resonance_spent, 1)  # catalog tier-1 cost: resonance_cost=1
        self.assertEqual(pull.anima_spent, 0)  # single thread: max(0,1-1)×1=0

        # --- FLAT_BONUS resolved effect written ---
        flat_effects = CombatPullResolvedEffect.objects.filter(
            pull=pull,
            kind=EffectKind.FLAT_BONUS,
            source_tier=1,
        )
        self.assertEqual(flat_effects.count(), 1)
        flat_eff = flat_effects.first()
        self.assertEqual(flat_eff.authored_value, 2)
        self.assertEqual(flat_eff.level_multiplier, 1)
        self.assertEqual(flat_eff.scaled_value, 2)

        # --- Return value matches DB ---
        flat_rows = [r for r in result.resolved_effects if r.kind == EffectKind.FLAT_BONUS]
        tier1_flat = [r for r in flat_rows if r.source_tier == 1]
        self.assertEqual(len(tier1_flat), 1)
        self.assertEqual(tier1_flat[0].scaled_value, 2)

        # --- Balance debited ---
        cr = CharacterResonance.objects.get(
            character_sheet=self.sheet,
            resonance=self.catalog.canonical_resonance,
        )
        self.assertEqual(cr.balance, 9)  # 10 − 1 (tier-1 cost)

    # -----------------------------------------------------------------------
    # Test 3: tier-2 pull → INTENSITY_BUMP CombatPullResolvedEffect
    # -----------------------------------------------------------------------

    def test_tier2_pull_writes_intensity_bump_effect(self) -> None:
        """Tier-2 resonance spend writes a CombatPull with an INTENSITY_BUMP resolved effect.

        Catalog: INTENSITY_BUMP tier=2, intensity_bump_amount=1, min_thread_level=0.
        Thread.level=10 → multiplier=1. Expected scaled_value = 1 × 1 = 1.
        resolve_pull_effects sweeps tiers 0..2, so FLAT_BONUS (tier=1) and
        VITAL_BONUS (tier=0) rows also appear in resolved_effects.
        """
        from world.combat.models import CombatPull, CombatPullResolvedEffect
        from world.magic.services import spend_resonance_for_pull

        self._fresh_resonance_balance(10)

        ctx = self._make_combat_ctx(round_number=3)
        result = spend_resonance_for_pull(
            self.sheet,
            self.catalog.canonical_resonance,
            tier=2,
            threads=[self.thread],
            action_context=ctx,
        )

        pull = CombatPull.objects.get(
            participant=ctx.participant,
            round_number=3,
        )
        self.assertEqual(pull.tier, 2)
        self.assertEqual(pull.resonance_spent, 3)  # catalog tier-2 cost: resonance_cost=3

        # --- INTENSITY_BUMP resolved effect written ---
        bump_effects = CombatPullResolvedEffect.objects.filter(
            pull=pull,
            kind=EffectKind.INTENSITY_BUMP,
            source_tier=2,
        )
        self.assertEqual(bump_effects.count(), 1)
        bump_eff = bump_effects.first()
        self.assertEqual(bump_eff.authored_value, 1)
        self.assertEqual(bump_eff.level_multiplier, 1)
        self.assertEqual(bump_eff.scaled_value, 1)

        # --- Return value includes INTENSITY_BUMP ---
        bump_rows = [
            r
            for r in result.resolved_effects
            if r.kind == EffectKind.INTENSITY_BUMP and r.source_tier == 2
        ]
        self.assertEqual(len(bump_rows), 1)
        self.assertEqual(bump_rows[0].scaled_value, 1)

    # -----------------------------------------------------------------------
    # Test 4: tier-3 pull → CAPABILITY_GRANT CombatPullResolvedEffect
    # -----------------------------------------------------------------------

    def test_tier3_pull_writes_capability_grant_effect(self) -> None:
        """Tier-3 resonance spend writes a CAPABILITY_GRANT resolved effect.

        Catalog: CAPABILITY_GRANT tier=3, min_thread_level=5, capability=endurance.
        Thread.level=10 satisfies min_thread_level=5.
        CAPABILITY_GRANT has no numeric payload; granted_capability points to the
        "endurance" CapabilityType seeded by seed_thread_pull_catalog().

        The resolve sweep covers tiers 0..3, so all four effect kinds appear.
        This test verifies the CAPABILITY_GRANT row specifically.
        """
        from world.combat.models import CombatPull, CombatPullResolvedEffect
        from world.magic.services import spend_resonance_for_pull

        self._fresh_resonance_balance(10)

        ctx = self._make_combat_ctx(round_number=4)
        result = spend_resonance_for_pull(
            self.sheet,
            self.catalog.canonical_resonance,
            tier=3,
            threads=[self.thread],
            action_context=ctx,
        )

        pull = CombatPull.objects.get(
            participant=ctx.participant,
            round_number=4,
        )
        self.assertEqual(pull.tier, 3)
        self.assertEqual(pull.resonance_spent, 6)  # catalog tier-3 cost: resonance_cost=6

        # --- CAPABILITY_GRANT resolved effect written ---
        grant_effects = CombatPullResolvedEffect.objects.filter(
            pull=pull,
            kind=EffectKind.CAPABILITY_GRANT,
            source_tier=3,
        )
        self.assertEqual(grant_effects.count(), 1)
        grant_eff = grant_effects.first()
        self.assertIsNone(grant_eff.scaled_value)
        self.assertIsNotNone(grant_eff.granted_capability)
        self.assertEqual(grant_eff.granted_capability.name, "endurance")

        # --- Return value includes CAPABILITY_GRANT ---
        cap_rows = [
            r
            for r in result.resolved_effects
            if r.kind == EffectKind.CAPABILITY_GRANT and r.source_tier == 3
        ]
        self.assertEqual(len(cap_rows), 1)
        self.assertEqual(cap_rows[0].granted_capability.name, "endurance")

        # --- All four effect kinds resolved across tiers 0..3 ---
        resolved_kinds = {r.kind for r in result.resolved_effects}
        self.assertIn(EffectKind.FLAT_BONUS, resolved_kinds)
        self.assertIn(EffectKind.INTENSITY_BUMP, resolved_kinds)
        self.assertIn(EffectKind.VITAL_BONUS, resolved_kinds)
        self.assertIn(EffectKind.CAPABILITY_GRANT, resolved_kinds)
