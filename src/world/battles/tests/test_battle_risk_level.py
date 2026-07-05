"""Tests for Battle.risk_level field (#1873)."""

from django.test import TestCase

from world.battles.factories import BattleFactory
from world.battles.services import create_battle
from world.combat.constants import RiskLevel


class BattleRiskLevelTests(TestCase):
    def test_battle_has_risk_level_default_low(self):
        battle = BattleFactory()
        self.assertEqual(battle.risk_level, RiskLevel.LOW)

    def test_create_battle_accepts_risk_level(self):
        battle = create_battle(name="Lethal Siege", risk_level=RiskLevel.LETHAL)
        self.assertEqual(battle.risk_level, RiskLevel.LETHAL)

    def test_create_battle_defaults_risk_level(self):
        battle = create_battle(name="Skirmish")
        self.assertEqual(battle.risk_level, RiskLevel.LOW)
