"""Tests for compute_opponent_stat_block and get_encounter_scaling_config (Task 3, #566).

Covers:
- test_tier_differentiation: BOSS block max_health > ELITE > MOOK at same encounter/party
- test_risk_multiplier_monotonic: LETHAL block > LOW block at same tier/party
- test_party_scaling: bigger party / higher avg_level → bigger max_health
- test_invariant_threads_irrelevant: identical size+levels, one thread-rich → same block
- test_boss_phase_generation: BOSS → boss_phase_count PhaseSpecs with descending triggers
- test_hero_killer_unscaled: HERO_KILLER block equals template base regardless of risk/party
"""

from django.test import TestCase

from world.classes.factories import CharacterClassLevelFactory
from world.combat.constants import (
    OpponentTier,
    ParticipantStatus,
    RiskLevel,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
    EncounterScalingConfigFactory,
    seed_scaling_defaults,
)
from world.combat.scaling import (
    OpponentStatBlock,
    PhaseSpec,
    compute_opponent_stat_block,
    get_encounter_scaling_config,
)


def _seed_and_encounter(risk_level: str = RiskLevel.MODERATE):
    """Seed scaling defaults and create a simple encounter at the given risk level."""
    seed_scaling_defaults()
    return CombatEncounterFactory(risk_level=risk_level)


def _add_participants(encounter, count: int, level: int):
    """Add *count* ACTIVE participants at *level* to *encounter*."""
    for _ in range(count):
        participant = CombatParticipantFactory(
            encounter=encounter,
            status=ParticipantStatus.ACTIVE,
        )
        CharacterClassLevelFactory(
            character=participant.character_sheet,
            level=level,
            is_primary=True,
        )


class GetEncounterScalingConfigSelfSeedTest(TestCase):
    """get_encounter_scaling_config() creates pk=1 on first use; does not seed lookup tables."""

    def test_returns_config_when_absent(self):
        """Should create the singleton if the table is empty."""
        from world.combat.models import EncounterScalingConfig

        self.assertEqual(EncounterScalingConfig.objects.filter(pk=1).count(), 0)
        cfg = get_encounter_scaling_config()
        self.assertEqual(cfg.pk, 1)

    def test_returns_existing_config(self):
        """Should reuse the row created by the factory."""
        EncounterScalingConfigFactory()
        cfg = get_encounter_scaling_config()
        self.assertEqual(cfg.pk, 1)

    def test_idempotent_no_duplicate(self):
        from world.combat.models import EncounterScalingConfig

        get_encounter_scaling_config()
        get_encounter_scaling_config()
        self.assertEqual(EncounterScalingConfig.objects.count(), 1)

    def test_does_not_seed_lookup_tables(self):
        """Accessor must NOT touch OpponentTierTemplate or RiskScalingModifier.

        The old implementation called seed_scaling_defaults() as a side effect,
        which would silently reset staff-tuned template/risk/stakes rows.
        This test verifies the side effect is gone.
        """
        from world.combat.models import OpponentTierTemplate, RiskScalingModifier

        self.assertEqual(OpponentTierTemplate.objects.count(), 0)
        self.assertEqual(RiskScalingModifier.objects.count(), 0)
        get_encounter_scaling_config()
        self.assertEqual(OpponentTierTemplate.objects.count(), 0)
        self.assertEqual(RiskScalingModifier.objects.count(), 0)


class TierDifferentiationTest(TestCase):
    """BOSS block max_health > ELITE > MOOK at same encounter/party."""

    @classmethod
    def setUpTestData(cls):
        seed_scaling_defaults()
        cls.encounter = CombatEncounterFactory(risk_level=RiskLevel.MODERATE)
        _add_participants(cls.encounter, count=4, level=5)

    def test_boss_health_greater_than_elite(self):
        boss_block = compute_opponent_stat_block(
            OpponentTier.BOSS, self.encounter, party_size=4, avg_level=5.0
        )
        elite_block = compute_opponent_stat_block(
            OpponentTier.ELITE, self.encounter, party_size=4, avg_level=5.0
        )
        self.assertGreater(boss_block.max_health, elite_block.max_health)

    def test_elite_health_greater_than_mook(self):
        elite_block = compute_opponent_stat_block(
            OpponentTier.ELITE, self.encounter, party_size=4, avg_level=5.0
        )
        mook_block = compute_opponent_stat_block(
            OpponentTier.MOOK, self.encounter, party_size=4, avg_level=5.0
        )
        self.assertGreater(elite_block.max_health, mook_block.max_health)

    def test_returns_opponent_stat_block(self):
        block = compute_opponent_stat_block(
            OpponentTier.MOOK, self.encounter, party_size=4, avg_level=5.0
        )
        self.assertIsInstance(block, OpponentStatBlock)

    def test_stat_block_is_frozen(self):
        block = compute_opponent_stat_block(
            OpponentTier.MOOK, self.encounter, party_size=4, avg_level=5.0
        )
        with self.assertRaises((AttributeError, TypeError)):
            block.max_health = 999  # type: ignore[misc]


class RiskMultiplierMonotonicTest(TestCase):
    """LETHAL block max_health > LOW block max_health at same tier/party."""

    @classmethod
    def setUpTestData(cls):
        seed_scaling_defaults()
        cls.encounter_low = CombatEncounterFactory(risk_level=RiskLevel.LOW)
        cls.encounter_lethal = CombatEncounterFactory(risk_level=RiskLevel.LETHAL)

    def test_lethal_health_greater_than_low(self):
        low_block = compute_opponent_stat_block(
            OpponentTier.ELITE, self.encounter_low, party_size=4, avg_level=5.0
        )
        lethal_block = compute_opponent_stat_block(
            OpponentTier.ELITE, self.encounter_lethal, party_size=4, avg_level=5.0
        )
        self.assertGreater(lethal_block.max_health, low_block.max_health)

    def test_lethal_soak_greater_than_low(self):
        low_block = compute_opponent_stat_block(
            OpponentTier.BOSS, self.encounter_low, party_size=4, avg_level=5.0
        )
        lethal_block = compute_opponent_stat_block(
            OpponentTier.BOSS, self.encounter_lethal, party_size=4, avg_level=5.0
        )
        self.assertGreater(lethal_block.soak_value, low_block.soak_value)

    def test_missing_risk_row_falls_back_to_one(self):
        """A missing RiskScalingModifier row must not raise — fall back to ×1.0."""
        from world.combat.models import RiskScalingModifier

        encounter = CombatEncounterFactory(risk_level=RiskLevel.HIGH)
        # Only seed templates and config — leave RiskScalingModifier empty for HIGH
        seed_scaling_defaults()
        RiskScalingModifier.objects.filter(risk_level=RiskLevel.HIGH).delete()

        # Should not raise DoesNotExist
        block = compute_opponent_stat_block(
            OpponentTier.MOOK, encounter, party_size=4, avg_level=5.0
        )
        self.assertIsInstance(block, OpponentStatBlock)


class PartyScalingTest(TestCase):
    """Bigger party / higher avg_level → bigger max_health."""

    @classmethod
    def setUpTestData(cls):
        seed_scaling_defaults()
        cls.encounter = CombatEncounterFactory(risk_level=RiskLevel.MODERATE)

    def test_larger_party_gives_bigger_health(self):
        small_block = compute_opponent_stat_block(
            OpponentTier.ELITE, self.encounter, party_size=2, avg_level=5.0
        )
        large_block = compute_opponent_stat_block(
            OpponentTier.ELITE, self.encounter, party_size=8, avg_level=5.0
        )
        self.assertGreater(large_block.max_health, small_block.max_health)

    def test_higher_avg_level_gives_bigger_health(self):
        low_level_block = compute_opponent_stat_block(
            OpponentTier.ELITE, self.encounter, party_size=4, avg_level=1.0
        )
        high_level_block = compute_opponent_stat_block(
            OpponentTier.ELITE, self.encounter, party_size=4, avg_level=10.0
        )
        self.assertGreater(high_level_block.max_health, low_level_block.max_health)

    def test_party_from_encounter_when_none(self):
        """When party_size/avg_level are None, profile is derived from the encounter."""
        _add_participants(self.encounter, count=4, level=5)
        block = compute_opponent_stat_block(OpponentTier.MOOK, self.encounter)
        self.assertIsInstance(block, OpponentStatBlock)
        self.assertGreater(block.max_health, 0)


class InvariantThreadsIrrelevantTest(TestCase):
    """Two parties with identical size+levels yield identical blocks regardless of covenant roles.

    Covenant roles are "threads" — the scaling invariant says they must not affect the block.
    """

    @classmethod
    def setUpTestData(cls):
        seed_scaling_defaults()
        cls.encounter_plain = CombatEncounterFactory(risk_level=RiskLevel.MODERATE)
        cls.encounter_threaded = CombatEncounterFactory(risk_level=RiskLevel.MODERATE)

        # Plain encounter: 3 active participants at level 4
        _add_participants(cls.encounter_plain, count=3, level=4)

        # Threaded encounter: same levels but participants have a covenant_role
        from world.covenants.factories import CovenantRoleFactory

        role = CovenantRoleFactory()
        for _ in range(3):
            participant = CombatParticipantFactory(
                encounter=cls.encounter_threaded,
                status=ParticipantStatus.ACTIVE,
                covenant_role=role,
            )
            CharacterClassLevelFactory(
                character=participant.character_sheet,
                level=4,
                is_primary=True,
            )

    def test_identical_block_regardless_of_covenant_role(self):
        block_plain = compute_opponent_stat_block(OpponentTier.ELITE, self.encounter_plain)
        block_threaded = compute_opponent_stat_block(OpponentTier.ELITE, self.encounter_threaded)
        self.assertEqual(block_plain, block_threaded)

    def test_expected_values_for_known_config(self):
        """Pin exact computed values for ELITE at MODERATE risk, party_size=3, avg_level=4.

        Formula (seeded defaults):
            baseline_party_size = 4, per_extra_member_pct = 0.15, per_avg_level_pct = 0.05
            extra_members = max(0, 3 - 4) = 0
            party_mult = 1 + 0.15 * 0 + 0.05 * 4.0 = 1.20
            risk_mult = 1.00  (MODERATE)
            max_health = round(80 * 1.00 * 1.20) = 96
            soak_value = round(3 * 1.00) = 3

        Pinning these integers catches formula drift that relational ordering tests
        would miss (e.g. scaling both up equally would preserve ordering but break
        the budget).
        """
        block = compute_opponent_stat_block(
            OpponentTier.ELITE, self.encounter_plain, party_size=3, avg_level=4.0
        )
        self.assertEqual(block.max_health, 96)
        self.assertEqual(block.soak_value, 3)


class BossPhaseGenerationTest(TestCase):
    """BOSS tier → boss_phase_count PhaseSpecs with descending health triggers."""

    @classmethod
    def setUpTestData(cls):
        seed_scaling_defaults()
        cls.encounter = CombatEncounterFactory(risk_level=RiskLevel.MODERATE)

    def test_boss_has_phase_count_phases(self):
        from world.combat.models import OpponentTierTemplate

        boss_tpl = OpponentTierTemplate.objects.get(tier=OpponentTier.BOSS)
        block = compute_opponent_stat_block(
            OpponentTier.BOSS, self.encounter, party_size=4, avg_level=5.0
        )
        self.assertEqual(len(block.phases), boss_tpl.boss_phase_count)

    def test_boss_phases_are_phase_spec_instances(self):
        block = compute_opponent_stat_block(
            OpponentTier.BOSS, self.encounter, party_size=4, avg_level=5.0
        )
        for phase in block.phases:
            self.assertIsInstance(phase, PhaseSpec)

    def test_boss_phase_1_trigger_is_none_or_100(self):
        """Phase 1 is active from full health — trigger is None or 100.0."""
        block = compute_opponent_stat_block(
            OpponentTier.BOSS, self.encounter, party_size=4, avg_level=5.0
        )
        p1 = block.phases[0]
        self.assertEqual(p1.phase_number, 1)
        self.assertTrue(
            p1.health_trigger_percentage is None or p1.health_trigger_percentage == 100.0,
            f"Phase 1 trigger should be None or 100.0, got {p1.health_trigger_percentage}",
        )

    def test_boss_phases_descending_triggers(self):
        """Phases 2+ have strictly descending health trigger percentages."""
        block = compute_opponent_stat_block(
            OpponentTier.BOSS, self.encounter, party_size=4, avg_level=5.0
        )
        triggers = [
            p.health_trigger_percentage
            for p in block.phases[1:]  # skip phase 1 (None or 100.0)
            if p.health_trigger_percentage is not None
        ]
        self.assertTrue(
            all(triggers[i] > triggers[i + 1] for i in range(len(triggers) - 1)),
            f"Triggers not strictly descending: {triggers}",
        )

    def test_boss_phase_soak_matches_block(self):
        """Each PhaseSpec's soak_value matches the computed block's soak_value."""
        block = compute_opponent_stat_block(
            OpponentTier.BOSS, self.encounter, party_size=4, avg_level=5.0
        )
        for phase in block.phases:
            self.assertEqual(phase.soak_value, block.soak_value)

    def test_mook_has_empty_phases(self):
        """Non-boss tiers have an empty phases tuple."""
        block = compute_opponent_stat_block(
            OpponentTier.MOOK, self.encounter, party_size=4, avg_level=5.0
        )
        self.assertEqual(block.phases, ())

    def test_elite_has_empty_phases(self):
        block = compute_opponent_stat_block(
            OpponentTier.ELITE, self.encounter, party_size=4, avg_level=5.0
        )
        self.assertEqual(block.phases, ())


class HeroKillerUnscaledTest(TestCase):
    """HERO_KILLER returns template base stats — risk/party multipliers do not apply."""

    @classmethod
    def setUpTestData(cls):
        seed_scaling_defaults()
        cls.encounter_low = CombatEncounterFactory(risk_level=RiskLevel.LOW)
        cls.encounter_lethal = CombatEncounterFactory(risk_level=RiskLevel.LETHAL)

    def test_hero_killer_health_unscaled_across_risk(self):
        from world.combat.models import OpponentTierTemplate

        tpl = OpponentTierTemplate.objects.get(tier=OpponentTier.HERO_KILLER)

        block_low = compute_opponent_stat_block(
            OpponentTier.HERO_KILLER, self.encounter_low, party_size=2, avg_level=1.0
        )
        block_lethal = compute_opponent_stat_block(
            OpponentTier.HERO_KILLER, self.encounter_lethal, party_size=8, avg_level=20.0
        )

        # All blocks should equal the raw template values
        self.assertEqual(block_low.max_health, tpl.base_health)
        self.assertEqual(block_lethal.max_health, tpl.base_health)

    def test_hero_killer_blocks_identical_regardless_of_party(self):
        """Different party sizes/levels yield identical HERO_KILLER blocks."""
        block_small = compute_opponent_stat_block(
            OpponentTier.HERO_KILLER, self.encounter_low, party_size=1, avg_level=1.0
        )
        block_large = compute_opponent_stat_block(
            OpponentTier.HERO_KILLER, self.encounter_lethal, party_size=10, avg_level=20.0
        )
        self.assertEqual(block_small, block_large)

    def test_hero_killer_soak_equals_template(self):
        from world.combat.models import OpponentTierTemplate

        tpl = OpponentTierTemplate.objects.get(tier=OpponentTier.HERO_KILLER)
        block = compute_opponent_stat_block(
            OpponentTier.HERO_KILLER, self.encounter_lethal, party_size=4, avg_level=5.0
        )
        self.assertEqual(block.soak_value, tpl.base_soak)


class NullOptionalFieldsTest(TestCase):
    """probing_threshold / barrier_strength None passthrough; no coercion to 0."""

    @classmethod
    def setUpTestData(cls):
        seed_scaling_defaults()
        cls.encounter = CombatEncounterFactory(risk_level=RiskLevel.MODERATE)

    def test_mook_probing_threshold_stays_none(self):
        block = compute_opponent_stat_block(
            OpponentTier.MOOK, self.encounter, party_size=4, avg_level=5.0
        )
        self.assertIsNone(block.probing_threshold)

    def test_boss_probing_threshold_not_none(self):
        block = compute_opponent_stat_block(
            OpponentTier.BOSS, self.encounter, party_size=4, avg_level=5.0
        )
        self.assertIsNotNone(block.probing_threshold)

    def test_swarm_count_scales_with_party(self):
        """Swarm's swarm_count scales with party multiplier."""
        block_small = compute_opponent_stat_block(
            OpponentTier.SWARM, self.encounter, party_size=2, avg_level=5.0
        )
        block_large = compute_opponent_stat_block(
            OpponentTier.SWARM, self.encounter, party_size=8, avg_level=5.0
        )
        self.assertGreater(block_large.swarm_count, block_small.swarm_count)

    def test_mook_swarm_count_is_none(self):
        block = compute_opponent_stat_block(
            OpponentTier.MOOK, self.encounter, party_size=4, avg_level=5.0
        )
        self.assertIsNone(block.swarm_count)
