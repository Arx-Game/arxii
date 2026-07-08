"""Tests for phase enrage: damage_multiplier and extra_actions."""

from decimal import Decimal

from django.test import TestCase

from world.combat.constants import OpponentTier
from world.combat.factories import (
    BossPhaseFactory,
    CombatEncounterFactory,
    CombatOpponentFactory,
)
from world.combat.services import check_and_advance_boss_phase


class EnrageTests(TestCase):
    def test_phase_transition_stamps_damage_multiplier(self):
        encounter = CombatEncounterFactory()
        opp = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.BOSS,
            max_health=100,
            health=100,
            soak_value=0,
            current_phase=1,
            actions_per_round=2,
        )
        BossPhaseFactory(
            opponent=opp,
            phase_number=2,
            health_trigger_percentage=0.67,
            soak_value=8,
            damage_multiplier=Decimal("1.5"),
            extra_actions=1,
            actions_per_round=3,
        )
        # Drop health below 67%
        opp.health = 66
        opp.save(update_fields=["health"])

        phase = check_and_advance_boss_phase(opp)
        self.assertIsNotNone(phase)
        opp.refresh_from_db()
        self.assertEqual(opp.damage_multiplier, Decimal("1.5"))
        # actions_per_round = phase override (3) + extra_actions (1) = 4
        self.assertEqual(opp.actions_per_round, 4)
        self.assertEqual(opp.soak_value, 8)

    def test_phase_transition_null_override_keeps_actions_plus_extra(self):
        """When actions_per_round is null on the phase, keep current + extra_actions."""
        encounter = CombatEncounterFactory()
        opp = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.BOSS,
            max_health=100,
            health=100,
            current_phase=1,
            actions_per_round=2,
        )
        BossPhaseFactory(
            opponent=opp,
            phase_number=2,
            health_trigger_percentage=0.5,
            extra_actions=2,
            actions_per_round=None,
        )
        opp.health = 49
        opp.save(update_fields=["health"])

        check_and_advance_boss_phase(opp)
        opp.refresh_from_db()
        # 2 (current) + 2 (extra) = 4
        self.assertEqual(opp.actions_per_round, 4)

    def test_no_phase_transition_leaves_multiplier_unchanged(self):
        encounter = CombatEncounterFactory()
        opp = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.BOSS,
            max_health=100,
            health=100,
            current_phase=1,
            actions_per_round=2,
        )
        BossPhaseFactory(
            opponent=opp,
            phase_number=2,
            health_trigger_percentage=0.5,
            damage_multiplier=Decimal("2.0"),
        )
        # Health still above threshold
        opp.health = 90
        opp.save(update_fields=["health"])

        phase = check_and_advance_boss_phase(opp)
        self.assertIsNone(phase)
        opp.refresh_from_db()
        self.assertEqual(opp.damage_multiplier, Decimal("1.0"))
        self.assertEqual(opp.actions_per_round, 2)
