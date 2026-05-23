"""Tests for fire_clash_per_round and resolve_clash — consequence pool firing."""

from unittest.mock import patch

from django.test import TestCase

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from evennia_extensions.factories import ObjectDBFactory
from world.checks.constants import EffectTarget, EffectType
from world.checks.factories import ConsequenceEffectFactory, ConsequenceFactory
from world.combat.clash import fire_clash_per_round, resolve_clash
from world.combat.constants import ClashResolution, ClashStatus, OpponentTier
from world.combat.factories import ClashFactory, ClashRoundFactory
from world.combat.models import Clash, CombatOpponent
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.models import ConditionInstance
from world.mechanics.factories import PropertyFactory
from world.mechanics.models import ObjectProperty
from world.traits.factories import CheckOutcomeFactory


class FireClashPerRoundTests(TestCase):
    """Unit tests for fire_clash_per_round."""

    @classmethod
    def setUpTestData(cls) -> None:
        # Three CheckOutcome tiers: success (1), partial (0), failure (-1)
        cls.outcome_success = CheckOutcomeFactory(name="PerRound_Success", success_level=1)
        cls.outcome_partial = CheckOutcomeFactory(name="PerRound_Partial", success_level=0)
        cls.outcome_failure = CheckOutcomeFactory(name="PerRound_Failure", success_level=-1)

    def _make_clash_no_pool(self) -> object:
        """CLASH-flavor clash with no per-round pool."""
        return ClashFactory(per_round_consequence_pool=None, progress=0, pc_win_threshold=5)

    def _make_clash_with_pool(
        self,
        progress: int = 3,
        pc_win_threshold: int = 5,
        pool: object = None,
    ) -> object:
        """CLASH-flavor clash with a given pool and progress."""
        return ClashFactory(
            per_round_consequence_pool=pool,
            progress=progress,
            pc_win_threshold=pc_win_threshold,
        )

    # ------------------------------------------------------------------
    # test_no_pool_is_noop
    # ------------------------------------------------------------------

    def test_no_pool_is_noop(self) -> None:
        """Clash with per_round_consequence_pool=None returns None, no exceptions."""
        clash = self._make_clash_no_pool()
        clash_round = ClashRoundFactory(clash=clash)
        result = fire_clash_per_round(clash=clash, clash_round=clash_round)
        self.assertIsNone(result)

    # ------------------------------------------------------------------
    # test_no_matching_tier_returns_none
    # ------------------------------------------------------------------

    def test_no_matching_tier_returns_none(self) -> None:
        """Pool has only failure-tier entries; meter maps to success tier → None."""
        pool = ConsequencePoolFactory(name="FailureOnly")
        consequence = ConsequenceFactory(
            outcome_tier=self.outcome_failure, label="Failure Entry", weight=1
        )
        ConsequencePoolEntryFactory(pool=pool, consequence=consequence)

        # progress=3, threshold=5 → ratio=0.6 → band success (level=1)
        # Pool only has failure tier → no match → None
        clash = self._make_clash_with_pool(progress=3, pc_win_threshold=5, pool=pool)
        clash_round = ClashRoundFactory(clash=clash)
        result = fire_clash_per_round(clash=clash, clash_round=clash_round)
        self.assertIsNone(result)

    # ------------------------------------------------------------------
    # test_pc_ahead_selects_success_tier_consequence
    # ------------------------------------------------------------------

    def test_pc_ahead_selects_success_tier_consequence(self) -> None:
        """Meter well ahead (ratio >= 0.5) selects from the success-tier consequences.

        The factory-built clash opponent has no ObjectDB, so effect application is
        skipped.  This test exercises consequence *selection* only.
        """
        pool = ConsequencePoolFactory(name="Mixed")
        c_success = ConsequenceFactory(
            outcome_tier=self.outcome_success, label="Success Consequence", weight=10
        )
        c_failure = ConsequenceFactory(
            outcome_tier=self.outcome_failure, label="Failure Consequence", weight=10
        )
        ConsequencePoolEntryFactory(pool=pool, consequence=c_success)
        ConsequencePoolEntryFactory(pool=pool, consequence=c_failure)

        # progress=3, threshold=5 → ratio=0.6 → success band (level=1)
        clash = self._make_clash_with_pool(progress=3, pc_win_threshold=5, pool=pool)
        self.assertIsNone(
            clash.npc_opponent.objectdb,
            "factory-built opponent must have no ObjectDB — this test exercises selection only",
        )
        clash_round = ClashRoundFactory(clash=clash)
        result = fire_clash_per_round(clash=clash, clash_round=clash_round)

        self.assertIsNotNone(result)
        self.assertEqual(result.outcome_tier, self.outcome_success)

    # ------------------------------------------------------------------
    # test_pc_behind_selects_failure_tier_consequence
    # ------------------------------------------------------------------

    def test_pc_behind_selects_failure_tier_consequence(self) -> None:
        """Meter behind (ratio in [-0.5, -0.25)) selects from the failure-tier consequences.

        The factory-built clash opponent has no ObjectDB, so effect application is
        skipped.  This test exercises consequence *selection* only.
        """
        pool = ConsequencePoolFactory(name="NegativeMeter")
        c_success = ConsequenceFactory(
            outcome_tier=self.outcome_success, label="Success Consequence Neg", weight=10
        )
        c_failure = ConsequenceFactory(
            outcome_tier=self.outcome_failure, label="Failure Consequence Neg", weight=10
        )
        ConsequencePoolEntryFactory(pool=pool, consequence=c_success)
        ConsequencePoolEntryFactory(pool=pool, consequence=c_failure)

        # progress=-2, threshold=5 → ratio=-0.4 → failure band (-0.5 <= ratio < -0.25)
        clash = self._make_clash_with_pool(progress=-2, pc_win_threshold=5, pool=pool)
        self.assertIsNone(
            clash.npc_opponent.objectdb,
            "factory-built opponent must have no ObjectDB — this test exercises selection only",
        )
        clash_round = ClashRoundFactory(clash=clash)
        result = fire_clash_per_round(clash=clash, clash_round=clash_round)

        self.assertIsNotNone(result)
        self.assertEqual(result.outcome_tier, self.outcome_failure)

    # ------------------------------------------------------------------
    # test_effects_applied
    # ------------------------------------------------------------------

    def test_effects_applied(self) -> None:
        """ADD_PROPERTY effect on selected consequence lands on the NPC's ObjectDB."""
        prop = PropertyFactory(name="combat_marked")

        # Build: pool → entry → consequence → effect
        pool = ConsequencePoolFactory(name="EffectTest")
        consequence = ConsequenceFactory(
            outcome_tier=self.outcome_success, label="Mark NPC", weight=1
        )
        ConsequencePoolEntryFactory(pool=pool, consequence=consequence)
        ConsequenceEffectFactory(
            consequence=consequence,
            effect_type=EffectType.ADD_PROPERTY,
            target=EffectTarget.SELF,
            property=prop,
            property_value=1,
        )

        # Create an opponent with a real ObjectDB so effects can be applied.
        npc_objectdb = ObjectDBFactory(db_key="EffectTestNPC")
        from world.combat.factories import CombatEncounterFactory

        encounter = CombatEncounterFactory()
        opponent = CombatOpponent.objects.create(
            encounter=encounter,
            tier=OpponentTier.MOOK,
            name="EffectTestOpponent",
            health=50,
            max_health=50,
            objectdb=npc_objectdb,
            objectdb_is_ephemeral=False,
        )

        # progress=3, threshold=5 → success band
        clash = ClashFactory(
            encounter=encounter,
            npc_opponent=opponent,
            per_round_consequence_pool=pool,
            progress=3,
            pc_win_threshold=5,
        )
        clash_round = ClashRoundFactory(clash=clash)

        result = fire_clash_per_round(clash=clash, clash_round=clash_round)

        self.assertIsNotNone(result)
        self.assertEqual(result.outcome_tier, self.outcome_success)

        # Verify the property was applied to the NPC's ObjectDB.
        self.assertTrue(
            ObjectProperty.objects.filter(
                object=npc_objectdb,
                property=prop,
            ).exists(),
            "ADD_PROPERTY effect should have created an ObjectProperty on the NPC",
        )


class ResolveClashTests(TestCase):
    """Unit tests for resolve_clash — end-of-clash resolution pool firing."""

    @classmethod
    def setUpTestData(cls) -> None:
        # Three CheckOutcome tiers used across tests.
        cls.outcome_critical = CheckOutcomeFactory(name="Resolve_Critical", success_level=3)
        cls.outcome_partial = CheckOutcomeFactory(name="Resolve_Partial", success_level=0)
        cls.outcome_botch = CheckOutcomeFactory(name="Resolve_Botch", success_level=-2)

    # ------------------------------------------------------------------
    # test_marks_clash_resolved
    # ------------------------------------------------------------------

    def test_marks_clash_resolved(self) -> None:
        """resolve_clash sets status=RESOLVED, resolution, and resolved_round; persists to DB."""
        pool = ConsequencePoolFactory(name="Resolve_Empty")
        clash = ClashFactory(resolution_consequence_pool=pool, progress=3, pc_win_threshold=5)

        result = resolve_clash(clash=clash, resolution=ClashResolution.PC_DECISIVE, round_number=4)

        self.assertEqual(result.clash.status, ClashStatus.RESOLVED)
        self.assertEqual(result.clash.resolution, ClashResolution.PC_DECISIVE)
        self.assertEqual(result.clash.resolved_round, 4)
        self.assertEqual(result.resolution, ClashResolution.PC_DECISIVE)

        # Confirm persistence.
        refreshed = Clash.objects.get(pk=clash.pk)
        self.assertEqual(refreshed.status, ClashStatus.RESOLVED)
        self.assertEqual(refreshed.resolution, ClashResolution.PC_DECISIVE)
        self.assertEqual(refreshed.resolved_round, 4)

    # ------------------------------------------------------------------
    # test_no_pool_resolves_without_consequence
    # ------------------------------------------------------------------

    def test_no_pool_resolves_without_consequence(self) -> None:
        """Empty pool (no entries) resolves without consequence_applied.

        Note: resolution_consequence_pool is a non-nullable FK, so we cannot
        pass None. This test exercises the "no matching tier" path using a pool
        with zero entries — the pool exists but yields no consequences, which is
        the closest equivalent to "no pool" for the resolution code path.
        """
        pool = ConsequencePoolFactory(name="Resolve_NoEntries")
        # No ConsequencePoolEntry rows created — pool is empty.
        clash = ClashFactory(resolution_consequence_pool=pool, progress=3, pc_win_threshold=5)

        result = resolve_clash(clash=clash, resolution=ClashResolution.PC_DECISIVE, round_number=2)

        self.assertIsNone(result.consequence_applied)
        self.assertEqual(result.clash.status, ClashStatus.RESOLVED)

    # ------------------------------------------------------------------
    # test_no_matching_tier_resolves_without_consequence
    # ------------------------------------------------------------------

    def test_no_matching_tier_resolves_without_consequence(self) -> None:
        """Pool has consequences for wrong tier; no match -> consequence_applied is None."""
        pool = ConsequencePoolFactory(name="Resolve_WrongTier")
        # Pool contains only a botch-tier consequence.
        c_botch = ConsequenceFactory(outcome_tier=self.outcome_botch, label="Botch Entry", weight=1)
        ConsequencePoolEntryFactory(pool=pool, consequence=c_botch)

        # Resolve with PC_DECISIVE -> maps to critical (success_level=3).
        # Pool only has botch tier -> no match.
        clash = ClashFactory(resolution_consequence_pool=pool, progress=3, pc_win_threshold=5)

        result = resolve_clash(clash=clash, resolution=ClashResolution.PC_DECISIVE, round_number=3)

        self.assertIsNone(result.consequence_applied)
        self.assertEqual(result.clash.status, ClashStatus.RESOLVED)

    # ------------------------------------------------------------------
    # test_pc_decisive_picks_critical_tier
    # ------------------------------------------------------------------

    def test_pc_decisive_picks_critical_tier(self) -> None:
        """PC_DECISIVE resolution selects the critical-tier consequence, not NPC-tier."""
        pool = ConsequencePoolFactory(name="Resolve_PCDecisive")
        c_critical = ConsequenceFactory(
            outcome_tier=self.outcome_critical, label="Critical Consequence", weight=10
        )
        c_botch = ConsequenceFactory(
            outcome_tier=self.outcome_botch, label="Botch Consequence", weight=10
        )
        ConsequencePoolEntryFactory(pool=pool, consequence=c_critical)
        ConsequencePoolEntryFactory(pool=pool, consequence=c_botch)

        # Factory clash opponent has no ObjectDB; effect application is skipped.
        clash = ClashFactory(resolution_consequence_pool=pool, progress=3, pc_win_threshold=5)
        self.assertIsNone(
            clash.npc_opponent.objectdb,
            "factory-built opponent must have no ObjectDB — this test exercises selection only",
        )

        result = resolve_clash(clash=clash, resolution=ClashResolution.PC_DECISIVE, round_number=5)

        self.assertIsNotNone(result.consequence_applied)
        self.assertEqual(result.consequence_applied.outcome_tier, self.outcome_critical)

    # ------------------------------------------------------------------
    # test_npc_decisive_picks_botch_tier
    # ------------------------------------------------------------------

    def test_npc_decisive_picks_botch_tier(self) -> None:
        """NPC_DECISIVE resolution selects the botch-tier consequence, not PC-tier."""
        pool = ConsequencePoolFactory(name="Resolve_NPCDecisive")
        c_critical = ConsequenceFactory(
            outcome_tier=self.outcome_critical, label="Critical NPC Entry", weight=10
        )
        c_botch = ConsequenceFactory(
            outcome_tier=self.outcome_botch, label="Botch NPC Entry", weight=10
        )
        ConsequencePoolEntryFactory(pool=pool, consequence=c_critical)
        ConsequencePoolEntryFactory(pool=pool, consequence=c_botch)

        clash = ClashFactory(resolution_consequence_pool=pool, progress=3, pc_win_threshold=5)
        self.assertIsNone(
            clash.npc_opponent.objectdb,
            "factory-built opponent must have no ObjectDB — this test exercises selection only",
        )

        result = resolve_clash(clash=clash, resolution=ClashResolution.NPC_DECISIVE, round_number=6)

        self.assertIsNotNone(result.consequence_applied)
        self.assertEqual(result.consequence_applied.outcome_tier, self.outcome_botch)

    # ------------------------------------------------------------------
    # test_window_state_condition_applied
    # ------------------------------------------------------------------

    def test_window_state_condition_applied(self) -> None:
        """APPLY_CONDITION effect in resolution pool creates a ConditionInstance on the NPC.

        This is the load-bearing test for the authored-content design: window-state
        conditions (e.g. 'boss held' for won Suppress, 'barrier down' for won BREAK)
        are produced by APPLY_CONDITION effects in the resolution pool -- no special-
        casing in resolve_clash itself.
        """
        boss_held = ConditionTemplateFactory(name="boss_held_suppress")
        pool = ConsequencePoolFactory(name="Resolve_WindowState")
        consequence = ConsequenceFactory(
            outcome_tier=self.outcome_critical, label="Boss Held", weight=1
        )
        ConsequencePoolEntryFactory(pool=pool, consequence=consequence)
        ConsequenceEffectFactory(
            consequence=consequence,
            effect_type=EffectType.APPLY_CONDITION,
            target=EffectTarget.SELF,
            condition_template=boss_held,
            condition_severity=1,
        )

        # Create opponent with a real ObjectDB so effects are applied.
        npc_objectdb = ObjectDBFactory(db_key="WindowStateNPC")
        from world.combat.factories import CombatEncounterFactory

        encounter = CombatEncounterFactory()
        opponent = CombatOpponent.objects.create(
            encounter=encounter,
            tier=OpponentTier.BOSS,
            name="WindowStateBoss",
            health=200,
            max_health=200,
            objectdb=npc_objectdb,
            objectdb_is_ephemeral=False,
        )
        clash = ClashFactory(
            encounter=encounter,
            npc_opponent=opponent,
            resolution_consequence_pool=pool,
            progress=5,
            pc_win_threshold=5,
        )

        result = resolve_clash(clash=clash, resolution=ClashResolution.PC_DECISIVE, round_number=7)

        self.assertIsNotNone(result.consequence_applied)

        # Load-bearing assertion: the ConditionInstance was created by authored
        # APPLY_CONDITION content, not by special-casing in resolve_clash.
        self.assertTrue(
            ConditionInstance.objects.filter(
                target=npc_objectdb,
                condition=boss_held,
            ).exists(),
            "APPLY_CONDITION effect in resolution pool must create a ConditionInstance on the NPC",
        )

    # ------------------------------------------------------------------
    # test_atomic_on_effect_failure
    # ------------------------------------------------------------------

    def test_atomic_on_effect_failure(self) -> None:
        """If effect application raises, the Clash status update is rolled back atomically."""
        pool = ConsequencePoolFactory(name="Resolve_Atomic")
        consequence = ConsequenceFactory(
            outcome_tier=self.outcome_critical, label="Atomic Consequence", weight=1
        )
        ConsequencePoolEntryFactory(pool=pool, consequence=consequence)
        # The consequence has no effects, but we'll patch apply_all_effects to raise.

        # Create opponent with a real ObjectDB (needed to reach apply_all_effects).
        npc_objectdb = ObjectDBFactory(db_key="AtomicTestNPC")
        from world.combat.factories import CombatEncounterFactory

        encounter = CombatEncounterFactory()
        opponent = CombatOpponent.objects.create(
            encounter=encounter,
            tier=OpponentTier.MOOK,
            name="AtomicOpponent",
            health=50,
            max_health=50,
            objectdb=npc_objectdb,
            objectdb_is_ephemeral=False,
        )
        clash = ClashFactory(
            encounter=encounter,
            npc_opponent=opponent,
            resolution_consequence_pool=pool,
            progress=5,
            pc_win_threshold=5,
        )
        original_status = clash.status

        with patch(
            "world.mechanics.effect_handlers.apply_all_effects",
            side_effect=RuntimeError("simulated effect failure"),
        ):
            with self.assertRaises(RuntimeError):
                resolve_clash(clash=clash, resolution=ClashResolution.PC_DECISIVE, round_number=8)

        # The Clash must NOT have been marked RESOLVED — atomic rollback.
        # Use values() to bypass SharedMemoryModel's identity-map cache, which
        # would return the in-memory RESOLVED state even after the DB rollback.
        row = Clash.objects.filter(pk=clash.pk).values("status", "resolution", "resolved_round")[0]
        self.assertEqual(
            row["status"],
            original_status,
            "Clash status must be rolled back when effect application raises",
        )
        self.assertIsNone(row["resolution"], "resolution must be rolled back on failure")
        self.assertIsNone(row["resolved_round"], "resolved_round must be rolled back on failure")
