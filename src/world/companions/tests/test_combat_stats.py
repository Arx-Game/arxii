"""Tests for CompanionArchetype combat stat fields (#1873)."""

from django.test import TestCase

from world.combat.constants import OpponentTier
from world.companions.factories import CompanionArchetypeFactory


class CompanionArchetypeCombatStatsTests(TestCase):
    def test_archetype_has_combat_stats_with_defaults(self):
        archetype = CompanionArchetypeFactory()
        self.assertEqual(archetype.max_health, 30)
        self.assertEqual(archetype.soak_value, 0)
        self.assertEqual(archetype.tier, OpponentTier.MOOK)
        self.assertEqual(archetype.strength, 5)

    def test_archetype_combat_stats_settable(self):
        archetype = CompanionArchetypeFactory(
            max_health=80,
            soak_value=15,
            tier=OpponentTier.ELITE,
            strength=50,
        )
        self.assertEqual(archetype.max_health, 80)
        self.assertEqual(archetype.soak_value, 15)
        self.assertEqual(archetype.tier, OpponentTier.ELITE)
        self.assertEqual(archetype.strength, 50)
