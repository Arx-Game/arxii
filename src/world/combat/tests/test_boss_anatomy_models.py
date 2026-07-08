"""Tests for boss-anatomy models: CreatureTemplate, CreaturePhaseTemplate, BreakBarConfig.

Also tests new fields on BossPhase, CombatOpponent, OpponentTierTemplate.
"""

from decimal import Decimal

from django.db import IntegrityError
from django.test import TestCase

from world.combat.constants import OpponentTier
from world.combat.factories import (
    CombatOpponentFactory,
    ThreatPoolFactory,
)
from world.combat.models import (
    BreakBarConfig,
    CreaturePhaseTemplate,
    CreatureTemplate,
    OpponentTierTemplate,
)


class CreatureTemplateTests(TestCase):
    def test_create_minimal_template(self):
        pool = ThreatPoolFactory()
        template = CreatureTemplate.objects.create(
            name="Test Boss",
            tier=OpponentTier.BOSS,
            threat_pool=pool,
        )
        self.assertEqual(template.name, "Test Boss")
        self.assertEqual(template.tier, OpponentTier.BOSS)
        self.assertEqual(template.threat_pool, pool)
        self.assertIsNone(template.soak_override)
        self.assertIsNone(template.probing_override)

    def test_str(self):
        template = CreatureTemplate.objects.create(
            name="Dragon",
            tier=OpponentTier.BOSS,
        )
        self.assertEqual(str(template), "Dragon")


class CreaturePhaseTemplateTests(TestCase):
    def test_create_phase_template(self):
        template = CreatureTemplate.objects.create(
            name="Boss",
            tier=OpponentTier.BOSS,
        )
        phase = CreaturePhaseTemplate.objects.create(
            creature_template=template,
            phase_number=1,
            soak_value=5,
            health_trigger_percentage=100.0,
            damage_multiplier=Decimal("1.5"),
            extra_actions=1,
        )
        self.assertEqual(phase.creature_template, template)
        self.assertEqual(phase.phase_number, 1)
        self.assertEqual(phase.damage_multiplier, Decimal("1.5"))
        self.assertEqual(phase.extra_actions, 1)

    def test_unique_phase_per_template(self):
        template = CreatureTemplate.objects.create(
            name="Boss",
            tier=OpponentTier.BOSS,
        )
        CreaturePhaseTemplate.objects.create(
            creature_template=template,
            phase_number=1,
        )
        with self.assertRaises(IntegrityError):
            CreaturePhaseTemplate.objects.create(
                creature_template=template,
                phase_number=1,
            )


class BreakBarConfigTests(TestCase):
    def test_create_config(self):
        template = CreatureTemplate.objects.create(
            name="Boss",
            tier=OpponentTier.BOSS,
        )
        phase = CreaturePhaseTemplate.objects.create(
            creature_template=template,
            phase_number=1,
        )
        config = BreakBarConfig.objects.create(
            boss_phase=phase,
            max_threshold=30,
            vulnerability_rounds=2,
            intensity_bonus=2,
        )
        self.assertEqual(config.max_threshold, 30)
        self.assertEqual(config.vulnerability_rounds, 2)
        self.assertEqual(config.intensity_bonus, 2)


class OpponentTierTemplateActionsPerRoundTests(TestCase):
    def test_default_is_1(self):
        tpl = OpponentTierTemplate.objects.create(
            tier=OpponentTier.MOOK,
            base_health=10,
        )
        self.assertEqual(tpl.base_actions_per_round, 1)


class CombatOpponentRuntimeFieldsTests(TestCase):
    def test_defaults(self):
        opp = CombatOpponentFactory()
        self.assertEqual(opp.actions_per_round, 1)
        self.assertEqual(opp.damage_multiplier, Decimal(1))
        self.assertEqual(opp.break_bar_threshold, 0)
        self.assertEqual(opp.break_bar_current, 0)
        self.assertEqual(opp.vulnerability_rounds_remaining, 0)
        self.assertEqual(opp.vulnerability_rounds, 0)
        self.assertEqual(opp.vulnerability_intensity_bonus, 0)
