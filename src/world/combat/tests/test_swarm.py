"""Swarm tier mechanics (#875): count-pool helpers, damage, offense, attrition arc."""

from django.test import TestCase

from world.combat.services import swarm_attack_count, swarm_kills


class SwarmHelperTests(TestCase):
    def test_swarm_kills_floor_with_minimum_one(self):
        # 5 damage per body: 12 damage clears 2 bodies.
        self.assertEqual(swarm_kills(12, body_toughness=5), 2)

    def test_swarm_kills_landing_hit_always_clears_one(self):
        # Damage below one body's toughness still clears a single body.
        self.assertEqual(swarm_kills(3, body_toughness=5), 1)

    def test_swarm_kills_zero_damage_clears_nothing(self):
        self.assertEqual(swarm_kills(0, body_toughness=5), 0)

    def test_swarm_attack_count_scales_with_count(self):
        # 30 bodies / 6 per attack = 5 attacks, capped at 4 acting PCs.
        self.assertEqual(swarm_attack_count(30, bodies_per_attack=6, active_pc_count=4), 4)

    def test_swarm_attack_count_shrinks_as_count_drops(self):
        self.assertEqual(swarm_attack_count(6, bodies_per_attack=6, active_pc_count=4), 1)

    def test_swarm_attack_count_zero_when_no_bodies_or_no_targets(self):
        self.assertEqual(swarm_attack_count(0, bodies_per_attack=6, active_pc_count=4), 0)
        self.assertEqual(swarm_attack_count(10, bodies_per_attack=6, active_pc_count=0), 0)
