"""Tests for tier-authored action economy."""

from django.test import TestCase

from world.combat.constants import OpponentTier
from world.combat.factories import (
    CombatEncounterFactory,
    EncounterScalingConfigFactory,
    OpponentTierTemplateFactory,
    RiskScalingModifierFactory,
)
from world.combat.scaling import compute_opponent_stat_block
from world.combat.services import add_opponent


class ActionEconomyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        EncounterScalingConfigFactory()
        for level in ("low", "moderate", "high", "extreme", "lethal"):
            RiskScalingModifierFactory(risk_level=level)
        cls.tpl = OpponentTierTemplateFactory(
            tier=OpponentTier.BOSS,
            base_health=100,
            base_soak=5,
            base_actions_per_round=3,
        )
        OpponentTierTemplateFactory(
            tier=OpponentTier.MOOK,
            base_health=20,
            base_soak=0,
            base_actions_per_round=1,
        )

    def test_stat_block_has_actions_per_round(self):
        encounter = CombatEncounterFactory()
        block = compute_opponent_stat_block(OpponentTier.BOSS, encounter)
        self.assertEqual(block.actions_per_round, 3)

    def test_add_opponent_stamps_actions_per_round(self):
        encounter = CombatEncounterFactory()
        opp = add_opponent(
            encounter,
            name="Boss",
            tier=OpponentTier.BOSS,
            threat_pool=None,
        )
        self.assertEqual(opp.actions_per_round, 3)

    def test_add_opponent_manual_mode_defaults_to_1(self):
        encounter = CombatEncounterFactory()
        opp = add_opponent(
            encounter,
            name="Manual Boss",
            tier=OpponentTier.BOSS,
            threat_pool=None,
            max_health=200,
        )
        self.assertEqual(opp.actions_per_round, 1)
