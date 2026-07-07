"""Tests for encounter scaling config models (Task 1, #566).

Covers:
- OpponentTierTemplate: per-tier stat rows, uniqueness, ordering
- RiskScalingModifier: per-risk multiplier rows, uniqueness, defaults
- StakesLevelRequirement: per-stakes requirement rows, uniqueness
- EncounterScalingConfig: pk=1 singleton defaults
- seed_scaling_defaults(): idempotent seeder
"""

from decimal import Decimal

from django.db.utils import IntegrityError
from django.test import TestCase

from world.combat.constants import (
    DEFAULT_RISK_MULTIPLIERS,
    DEFAULT_STAKES_REQUIREMENTS,
    DEFAULT_TIER_TEMPLATES,
    OpponentTier,
    RiskLevel,
    StakesLevel,
)
from world.combat.factories import (
    EncounterScalingConfigFactory,
    OpponentTierTemplateFactory,
    RiskScalingModifierFactory,
    StakesLevelRequirementFactory,
    seed_scaling_defaults,
)
from world.combat.models import (
    EncounterScalingConfig,
    OpponentTierTemplate,
    RiskScalingModifier,
    StakesLevelRequirement,
)
from world.gm.constants import GMLevel, gm_level_index


class OpponentTierTemplateModelTests(TestCase):
    """OpponentTierTemplate: per-tier stat rows."""

    @classmethod
    def setUpTestData(cls):
        cls.mook = OpponentTierTemplateFactory(
            tier=OpponentTier.MOOK,
            base_health=30,
            base_soak=0,
            base_probing_threshold=None,
            base_swarm_count=None,
            body_toughness=None,
            bodies_per_attack=None,
            barrier_strength=None,
            boss_phase_count=1,
        )
        cls.boss = OpponentTierTemplateFactory(
            tier=OpponentTier.BOSS,
            base_health=300,
            base_soak=8,
            base_probing_threshold=5,
            base_swarm_count=None,
            body_toughness=None,
            bodies_per_attack=None,
            barrier_strength=None,
            boss_phase_count=3,
        )
        cls.swarm = OpponentTierTemplateFactory(
            tier=OpponentTier.SWARM,
            base_health=0,
            base_soak=0,
            base_probing_threshold=None,
            base_swarm_count=20,
            body_toughness=5,
            bodies_per_attack=4,
            barrier_strength=None,
            boss_phase_count=1,
        )

    def test_boss_health_greater_than_mook(self):
        self.assertGreater(self.boss.base_health, self.mook.base_health)

    def test_boss_phase_count_greater_than_mook(self):
        self.assertGreater(self.boss.boss_phase_count, self.mook.boss_phase_count)

    def test_swarm_has_swarm_count(self):
        self.assertIsNotNone(self.swarm.base_swarm_count)
        self.assertGreater(self.swarm.base_swarm_count, 0)

    def test_mook_probing_threshold_null(self):
        self.assertIsNone(self.mook.base_probing_threshold)

    def test_tier_unique_constraint(self):
        with self.assertRaises(IntegrityError):
            OpponentTierTemplate.objects.create(
                tier=OpponentTier.MOOK,
                base_health=10,
                base_soak=0,
                boss_phase_count=1,
            )

    def test_str_contains_tier(self):
        self.assertIn("mook", str(self.mook).lower())

    def test_ordering_defined(self):
        # Meta.ordering must produce a consistent order — no exception is the minimum bar.
        qs = list(OpponentTierTemplate.objects.all())
        self.assertGreater(len(qs), 0)


class RiskScalingModifierModelTests(TestCase):
    """RiskScalingModifier: per-risk multiplier rows."""

    @classmethod
    def setUpTestData(cls):
        cls.low = RiskScalingModifierFactory(risk_level=RiskLevel.LOW, multiplier=Decimal("0.70"))
        cls.moderate = RiskScalingModifierFactory(
            risk_level=RiskLevel.MODERATE, multiplier=Decimal("1.00")
        )
        cls.lethal = RiskScalingModifierFactory(
            risk_level=RiskLevel.LETHAL, multiplier=Decimal("2.00")
        )

    def test_lethal_multiplier_greater_than_low(self):
        self.assertGreater(self.lethal.multiplier, self.low.multiplier)

    def test_moderate_default_is_one(self):
        self.assertEqual(self.moderate.multiplier, Decimal("1.00"))

    def test_risk_level_unique_constraint(self):
        with self.assertRaises(IntegrityError):
            RiskScalingModifier.objects.create(
                risk_level=RiskLevel.LOW,
                multiplier=Decimal("0.50"),
            )

    def test_str_contains_risk_level(self):
        self.assertIn("low", str(self.low).lower())

    def test_ordering_defined(self):
        qs = list(RiskScalingModifier.objects.all())
        self.assertGreater(len(qs), 0)


class StakesLevelRequirementModelTests(TestCase):
    """StakesLevelRequirement: per-stakes requirement rows."""

    @classmethod
    def setUpTestData(cls):
        cls.local = StakesLevelRequirementFactory(
            stakes_level=StakesLevel.LOCAL,
            minimum_party_average_level=0,
            minimum_gm_level=GMLevel.STARTING,
        )
        cls.world = StakesLevelRequirementFactory(
            stakes_level=StakesLevel.WORLD,
            minimum_party_average_level=20,
            minimum_gm_level=GMLevel.SENIOR,
        )

    def test_world_requires_higher_level_than_local(self):
        self.assertGreater(
            self.world.minimum_party_average_level,
            self.local.minimum_party_average_level,
        )

    def test_world_requires_higher_gm_level_than_local(self):
        self.assertGreater(
            gm_level_index(self.world.minimum_gm_level),
            gm_level_index(self.local.minimum_gm_level),
        )

    def test_local_gm_level_is_starting(self):
        self.assertEqual(self.local.minimum_gm_level, GMLevel.STARTING)

    def test_stakes_level_unique_constraint(self):
        with self.assertRaises(IntegrityError):
            StakesLevelRequirement.objects.create(
                stakes_level=StakesLevel.LOCAL,
                minimum_party_average_level=5,
                minimum_gm_level=GMLevel.JUNIOR,
            )

    def test_str_contains_stakes_level(self):
        self.assertIn("local", str(self.local).lower())

    def test_ordering_defined(self):
        qs = list(StakesLevelRequirement.objects.all())
        self.assertGreater(len(qs), 0)


class EncounterScalingConfigModelTests(TestCase):
    """EncounterScalingConfig: pk=1 singleton."""

    @classmethod
    def setUpTestData(cls):
        cls.config = EncounterScalingConfigFactory()

    def test_pk_is_1(self):
        self.assertEqual(self.config.pk, 1)

    def test_baseline_party_size_default(self):
        self.assertEqual(self.config.baseline_party_size, 4)

    def test_per_extra_member_pct_default(self):
        self.assertEqual(self.config.per_extra_member_pct, Decimal("0.15"))

    def test_per_avg_level_pct_default(self):
        self.assertEqual(self.config.per_avg_level_pct, Decimal("0.05"))

    def test_updated_by_nullable(self):
        self.assertIsNone(self.config.updated_by)

    def test_str(self):
        self.assertIn("1", str(self.config))

    def test_singleton_get_or_create(self):
        second = EncounterScalingConfigFactory()
        self.assertEqual(second.pk, 1)
        self.assertEqual(EncounterScalingConfig.objects.count(), 1)


class SeedScalingDefaultsTests(TestCase):
    """seed_scaling_defaults() seeds all four tables idempotently."""

    def test_seeds_tier_templates(self):
        seed_scaling_defaults()
        self.assertEqual(
            OpponentTierTemplate.objects.count(),
            len(DEFAULT_TIER_TEMPLATES),
        )

    def test_seeds_risk_modifiers(self):
        seed_scaling_defaults()
        self.assertEqual(
            RiskScalingModifier.objects.count(),
            len(DEFAULT_RISK_MULTIPLIERS),
        )

    def test_seeds_stakes_requirements(self):
        seed_scaling_defaults()
        self.assertEqual(
            StakesLevelRequirement.objects.count(),
            len(DEFAULT_STAKES_REQUIREMENTS),
        )

    def test_seeds_singleton_config(self):
        seed_scaling_defaults()
        self.assertEqual(EncounterScalingConfig.objects.count(), 1)
        config = EncounterScalingConfig.objects.get(pk=1)
        self.assertEqual(config.baseline_party_size, 4)

    def test_idempotent_no_duplicates(self):
        seed_scaling_defaults()
        seed_scaling_defaults()
        self.assertEqual(
            OpponentTierTemplate.objects.count(),
            len(DEFAULT_TIER_TEMPLATES),
        )
        self.assertEqual(
            RiskScalingModifier.objects.count(),
            len(DEFAULT_RISK_MULTIPLIERS),
        )
        self.assertEqual(
            StakesLevelRequirement.objects.count(),
            len(DEFAULT_STAKES_REQUIREMENTS),
        )
        self.assertEqual(EncounterScalingConfig.objects.count(), 1)

    def test_tier_boss_health_correct(self):
        seed_scaling_defaults()
        boss = OpponentTierTemplate.objects.get(tier=OpponentTier.BOSS)
        self.assertEqual(boss.base_health, DEFAULT_TIER_TEMPLATES[OpponentTier.BOSS]["base_health"])

    def test_risk_lethal_multiplier_correct(self):
        seed_scaling_defaults()
        lethal = RiskScalingModifier.objects.get(risk_level=RiskLevel.LETHAL)
        self.assertEqual(
            lethal.multiplier,
            Decimal(str(DEFAULT_RISK_MULTIPLIERS[RiskLevel.LETHAL])),
        )
