"""Tests for CreatureTemplate spawn_from_creature_template and compute_party_multiplier."""

from decimal import Decimal

from django.test import TestCase

from world.combat.constants import OpponentTier
from world.combat.factories import (
    CombatEncounterFactory,
    EncounterScalingConfigFactory,
    OpponentTierTemplateFactory,
    RiskScalingModifierFactory,
    ThreatPoolFactory,
)
from world.combat.models import BossPhase, BreakBarConfig, CreaturePhaseTemplate, CreatureTemplate
from world.combat.scaling import compute_party_multiplier
from world.combat.services import spawn_from_creature_template


class SpawnFromCreatureTemplateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        EncounterScalingConfigFactory()
        for level in ("low", "moderate", "high", "extreme", "lethal"):
            RiskScalingModifierFactory(risk_level=level)
        OpponentTierTemplateFactory(
            tier=OpponentTier.BOSS,
            base_health=100,
            base_soak=5,
            base_actions_per_round=2,
        )
        OpponentTierTemplateFactory(
            tier=OpponentTier.MOOK,
            base_health=20,
            base_soak=0,
        )

    def test_spawn_auto_phases(self):
        pool = ThreatPoolFactory()
        template = CreatureTemplate.objects.create(
            name="Boss",
            tier=OpponentTier.BOSS,
            threat_pool=pool,
        )
        encounter = CombatEncounterFactory()
        opp = spawn_from_creature_template(encounter, template)
        self.assertEqual(opp.name, "Boss")
        self.assertEqual(opp.tier, OpponentTier.BOSS)
        self.assertEqual(opp.threat_pool, pool)
        self.assertGreater(opp.max_health, 0)
        self.assertEqual(opp.actions_per_round, 2)

    def test_spawn_with_authored_phases(self):
        pool = ThreatPoolFactory()
        template = CreatureTemplate.objects.create(
            name="Phased Boss",
            tier=OpponentTier.BOSS,
            threat_pool=pool,
        )
        pt1 = CreaturePhaseTemplate.objects.create(
            creature_template=template,
            phase_number=1,
            health_trigger_percentage=1.0,
            soak_value=5,
            damage_multiplier=Decimal("1.0"),
        )
        CreaturePhaseTemplate.objects.create(
            creature_template=template,
            phase_number=2,
            health_trigger_percentage=0.5,
            soak_value=10,
            damage_multiplier=Decimal("1.5"),
            extra_actions=1,
        )
        BreakBarConfig.objects.create(
            boss_phase=pt1,
            max_threshold=30,
            vulnerability_rounds=2,
            intensity_bonus=2,
        )
        encounter = CombatEncounterFactory()
        opp = spawn_from_creature_template(encounter, template)
        phases = BossPhase.objects.filter(opponent=opp).order_by("phase_number")
        self.assertEqual(phases.count(), 2)
        self.assertEqual(phases[0].soak_value, 5)
        self.assertEqual(phases[1].soak_value, 10)
        self.assertEqual(phases[1].damage_multiplier, Decimal("1.5"))
        # Break bar stamped from config
        self.assertGreater(opp.break_bar_threshold, 0)
        self.assertEqual(opp.break_bar_current, opp.break_bar_threshold)
        self.assertEqual(opp.vulnerability_rounds, 2)
        self.assertEqual(opp.vulnerability_intensity_bonus, 2)


class ComputePartyMultiplierTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        EncounterScalingConfigFactory()

    def test_baseline_party(self):
        mult = compute_party_multiplier(party_size=4, avg_level=5)
        self.assertGreater(mult, 1)

    def test_smaller_party_is_lower_mult(self):
        large = compute_party_multiplier(party_size=6, avg_level=5)
        small = compute_party_multiplier(party_size=2, avg_level=5)
        self.assertGreater(large, small)
