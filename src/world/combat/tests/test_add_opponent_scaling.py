"""Tests for add_opponent auto-fill from compute_opponent_stat_block (Task 5, #566).

Covers:
- test_tier_only_fills_defaults: omitting all stat args fills them from the scaling formula
- test_boss_tier_generates_phases: BOSS tier auto-creates BossPhase rows from block.phases
- test_explicit_overrides_win: explicitly passed max_health=999 stays 999
- test_non_boss_tier_no_phases: non-BOSS tier never generates BossPhase rows
- test_auto_phases_false_skips_phase_creation: auto_phases=False suppresses phase creation
- test_existing_callers_explicit_max_health: existing callers that pass max_health keep working
"""

from django.test import TestCase

from world.combat.constants import OpponentTier, RiskLevel
from world.combat.factories import (
    CombatEncounterFactory,
    ThreatPoolFactory,
    seed_scaling_defaults,
)
from world.combat.models import BossPhase
from world.combat.scaling import compute_opponent_stat_block
from world.combat.services import add_opponent


class TierOnlyFillsDefaultsTest(TestCase):
    """add_opponent with no explicit stat args fills health/soak/probing from the formula."""

    @classmethod
    def setUpTestData(cls) -> None:
        seed_scaling_defaults()
        cls.encounter = CombatEncounterFactory(risk_level=RiskLevel.MODERATE)
        cls.pool = ThreatPoolFactory()

    def test_tier_only_fills_max_health(self) -> None:
        expected = compute_opponent_stat_block(OpponentTier.ELITE, self.encounter)
        opp = add_opponent(
            self.encounter,
            name="Scaled Elite",
            tier=OpponentTier.ELITE,
            threat_pool=self.pool,
        )
        self.assertEqual(opp.max_health, expected.max_health)

    def test_tier_only_fills_health_equals_max_health(self) -> None:
        opp = add_opponent(
            self.encounter,
            name="Scaled Elite 2",
            tier=OpponentTier.ELITE,
            threat_pool=self.pool,
        )
        self.assertEqual(opp.health, opp.max_health)

    def test_tier_only_fills_soak_value(self) -> None:
        expected = compute_opponent_stat_block(OpponentTier.ELITE, self.encounter)
        opp = add_opponent(
            self.encounter,
            name="Scaled Elite 3",
            tier=OpponentTier.ELITE,
            threat_pool=self.pool,
        )
        self.assertEqual(opp.soak_value, expected.soak_value)

    def test_tier_only_fills_probing_threshold(self) -> None:
        expected = compute_opponent_stat_block(OpponentTier.BOSS, self.encounter)
        boss_pool = ThreatPoolFactory()
        opp = add_opponent(
            self.encounter,
            name="Scaled Boss",
            tier=OpponentTier.BOSS,
            threat_pool=boss_pool,
        )
        self.assertEqual(opp.probing_threshold, expected.probing_threshold)

    def test_mook_probing_threshold_stays_none(self) -> None:
        """MOOK template has no probing — omitting it leaves it None."""
        expected = compute_opponent_stat_block(OpponentTier.MOOK, self.encounter)
        self.assertIsNone(expected.probing_threshold)
        opp = add_opponent(
            self.encounter,
            name="Mook Auto",
            tier=OpponentTier.MOOK,
            threat_pool=self.pool,
        )
        self.assertIsNone(opp.probing_threshold)


class BossTierGeneratesPhasesTest(TestCase):
    """BOSS tier-only call auto-creates BossPhase rows matching block.phases."""

    @classmethod
    def setUpTestData(cls) -> None:
        seed_scaling_defaults()
        cls.encounter = CombatEncounterFactory(risk_level=RiskLevel.MODERATE)
        cls.pool = ThreatPoolFactory()

    def test_boss_creates_boss_phase_rows(self) -> None:
        block = compute_opponent_stat_block(OpponentTier.BOSS, self.encounter)
        self.assertGreater(len(block.phases), 0, "Seeded BOSS template must have phases")

        opp = add_opponent(
            self.encounter,
            name="Auto Boss",
            tier=OpponentTier.BOSS,
            threat_pool=self.pool,
        )
        phases = list(BossPhase.objects.filter(opponent=opp).order_by("phase_number"))
        self.assertEqual(len(phases), len(block.phases))

    def test_boss_phase_numbers_match(self) -> None:
        block = compute_opponent_stat_block(OpponentTier.BOSS, self.encounter)
        opp = add_opponent(
            self.encounter,
            name="Auto Boss 2",
            tier=OpponentTier.BOSS,
            threat_pool=self.pool,
        )
        phases = list(BossPhase.objects.filter(opponent=opp).order_by("phase_number"))
        for db_phase, spec in zip(phases, block.phases, strict=True):
            self.assertEqual(db_phase.phase_number, spec.phase_number)

    def test_boss_phase_triggers_descend(self) -> None:
        """Phase triggers follow the descending pattern from the stat block."""
        block = compute_opponent_stat_block(OpponentTier.BOSS, self.encounter)
        opp = add_opponent(
            self.encounter,
            name="Auto Boss 3",
            tier=OpponentTier.BOSS,
            threat_pool=self.pool,
        )
        phases = list(BossPhase.objects.filter(opponent=opp).order_by("phase_number"))
        for db_phase, spec in zip(phases, block.phases, strict=True):
            self.assertEqual(db_phase.health_trigger_percentage, spec.health_trigger_percentage)

    def test_boss_phase_soak_from_block(self) -> None:
        block = compute_opponent_stat_block(OpponentTier.BOSS, self.encounter)
        opp = add_opponent(
            self.encounter,
            name="Auto Boss 4",
            tier=OpponentTier.BOSS,
            threat_pool=self.pool,
        )
        phases = list(BossPhase.objects.filter(opponent=opp))
        for db_phase in phases:
            self.assertEqual(db_phase.soak_value, block.soak_value)

    def test_boss_phase_threat_pool_is_none(self) -> None:
        """Auto-generated phases have no threat_pool (GM can assign later)."""
        opp = add_opponent(
            self.encounter,
            name="Auto Boss 5",
            tier=OpponentTier.BOSS,
            threat_pool=self.pool,
        )
        phases = list(BossPhase.objects.filter(opponent=opp))
        for db_phase in phases:
            self.assertIsNone(db_phase.threat_pool)


class ExplicitOverridesWinTest(TestCase):
    """Explicitly passed stat values always override the scaling formula."""

    @classmethod
    def setUpTestData(cls) -> None:
        seed_scaling_defaults()
        cls.encounter = CombatEncounterFactory(risk_level=RiskLevel.MODERATE)
        cls.pool = ThreatPoolFactory()

    def test_explicit_max_health_wins(self) -> None:
        block = compute_opponent_stat_block(OpponentTier.ELITE, self.encounter)
        # Ensure our explicit value differs from the formula
        explicit_hp = 999
        self.assertNotEqual(explicit_hp, block.max_health)

        opp = add_opponent(
            self.encounter,
            name="Override HP",
            tier=OpponentTier.ELITE,
            max_health=explicit_hp,
            threat_pool=self.pool,
        )
        self.assertEqual(opp.max_health, explicit_hp)
        self.assertEqual(opp.health, explicit_hp)

    def test_explicit_soak_wins(self) -> None:
        opp = add_opponent(
            self.encounter,
            name="Override Soak",
            tier=OpponentTier.ELITE,
            threat_pool=self.pool,
            soak_value=77,
        )
        self.assertEqual(opp.soak_value, 77)

    def test_explicit_probing_threshold_wins(self) -> None:
        opp = add_opponent(
            self.encounter,
            name="Override Probing",
            tier=OpponentTier.BOSS,
            threat_pool=self.pool,
            probing_threshold=99,
        )
        self.assertEqual(opp.probing_threshold, 99)

    def test_mixed_explicit_max_health_uses_legacy_soak_default(self) -> None:
        """When max_health is explicit, secondary stats use legacy defaults (soak=0).

        max_health is the trigger for auto-scaling mode.  A caller who provides
        max_health but omits soak_value gets the pre-scaling default of 0 — the
        same behavior as the original signature — preserving backward compatibility.
        """
        opp = add_opponent(
            self.encounter,
            name="Mixed",
            tier=OpponentTier.ELITE,
            max_health=999,
            threat_pool=self.pool,
        )
        self.assertEqual(opp.max_health, 999)
        self.assertEqual(opp.health, 999)
        # soak defaults to 0 in manual mode (max_health explicitly provided)
        self.assertEqual(opp.soak_value, 0)


class NonBossTierNoPhasesTest(TestCase):
    """Non-BOSS tiers must never auto-create BossPhase rows."""

    @classmethod
    def setUpTestData(cls) -> None:
        seed_scaling_defaults()
        cls.encounter = CombatEncounterFactory(risk_level=RiskLevel.MODERATE)
        cls.pool = ThreatPoolFactory()

    def test_mook_no_phases(self) -> None:
        opp = add_opponent(
            self.encounter,
            name="Mook No Phases",
            tier=OpponentTier.MOOK,
            threat_pool=self.pool,
        )
        self.assertEqual(BossPhase.objects.filter(opponent=opp).count(), 0)

    def test_elite_no_phases(self) -> None:
        opp = add_opponent(
            self.encounter,
            name="Elite No Phases",
            tier=OpponentTier.ELITE,
            threat_pool=self.pool,
        )
        self.assertEqual(BossPhase.objects.filter(opponent=opp).count(), 0)

    def test_swarm_no_phases(self) -> None:
        opp = add_opponent(
            self.encounter,
            name="Swarm No Phases",
            tier=OpponentTier.SWARM,
            threat_pool=self.pool,
        )
        self.assertEqual(BossPhase.objects.filter(opponent=opp).count(), 0)

    def test_swarm_max_count_mirrors_initial_count(self) -> None:
        # Auto-filled swarm: max_swarm_count must mirror the initial swarm_count
        # so a percentage-remaining display has a denominator.
        opp = add_opponent(
            self.encounter,
            name="Swarm Bodies",
            tier=OpponentTier.SWARM,
            threat_pool=self.pool,
        )
        self.assertIsNotNone(opp.swarm_count)
        self.assertEqual(opp.max_swarm_count, opp.swarm_count)


class AutoPhasesFalseTest(TestCase):
    """auto_phases=False suppresses BossPhase auto-creation even for BOSS tier."""

    @classmethod
    def setUpTestData(cls) -> None:
        seed_scaling_defaults()
        cls.encounter = CombatEncounterFactory(risk_level=RiskLevel.MODERATE)
        cls.pool = ThreatPoolFactory()

    def test_boss_auto_phases_false_no_rows(self) -> None:
        opp = add_opponent(
            self.encounter,
            name="Manual Boss",
            tier=OpponentTier.BOSS,
            threat_pool=self.pool,
            auto_phases=False,
        )
        self.assertEqual(BossPhase.objects.filter(opponent=opp).count(), 0)


class ExistingCallerCompatibilityTest(TestCase):
    """Existing callers that pass max_health explicitly must work unchanged.

    This mirrors the patterns in test_add_opponent.py and test_services.py
    to confirm backward compatibility.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        # Seed scaling defaults so compute_opponent_stat_block is callable,
        # but these tests must behave identically whether or not defaults are seeded.
        seed_scaling_defaults()
        cls.encounter = CombatEncounterFactory()
        cls.pool = ThreatPoolFactory()

    def test_explicit_max_health_50_mook(self) -> None:
        """Pattern from test_services.py: add_opponent(tier=MOOK, max_health=50)."""
        opp = add_opponent(
            self.encounter,
            name="Explicit Mook",
            tier=OpponentTier.MOOK,
            max_health=50,
            threat_pool=self.pool,
        )
        self.assertEqual(opp.max_health, 50)
        self.assertEqual(opp.health, 50)
        self.assertEqual(opp.tier, OpponentTier.MOOK)

    def test_explicit_max_health_500_boss_with_soak(self) -> None:
        """Pattern from test_services.py: add_opponent(tier=BOSS, max_health=500, soak_value=80)."""
        opp = add_opponent(
            self.encounter,
            name="Explicit Boss",
            tier=OpponentTier.BOSS,
            max_health=500,
            threat_pool=self.pool,
            soak_value=80,
            probing_threshold=50,
        )
        self.assertEqual(opp.max_health, 500)
        self.assertEqual(opp.soak_value, 80)
        self.assertEqual(opp.probing_threshold, 50)
        # Manual mode (max_health provided) computes no block → no auto phases.
        self.assertEqual(BossPhase.objects.filter(opponent=opp).count(), 0)
