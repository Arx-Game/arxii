"""Tests for the CombatNPC encounter-scoped typeclass."""

from evennia import create_object
from evennia.utils.test_resources import EvenniaTestCase


class CombatNPCTypeclassTests(EvenniaTestCase):
    def test_create_combat_npc(self):
        from world.combat.typeclasses.combat_npc import CombatNPC

        npc = create_object(CombatNPC, key="Test Mook")
        self.assertIsInstance(npc, CombatNPC)
        self.assertEqual(npc.key, "Test Mook")
