"""Tests for fire_clash_per_round — per-round consequence pool firing."""

from django.test import TestCase

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from evennia_extensions.factories import ObjectDBFactory
from world.checks.constants import EffectTarget, EffectType
from world.checks.factories import ConsequenceEffectFactory, ConsequenceFactory
from world.combat.clash import fire_clash_per_round
from world.combat.constants import OpponentTier
from world.combat.factories import ClashFactory, ClashRoundFactory
from world.combat.models import CombatOpponent
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
