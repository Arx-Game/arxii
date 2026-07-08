"""Tests for NPC reinforcement spawning and break-bar reset at phase transitions."""

from django.test import TestCase

from world.combat.constants import OpponentTier
from world.combat.factories import (
    BossPhaseFactory,
    CombatEncounterFactory,
    CombatOpponentFactory,
    ThreatPoolFactory,
)
from world.combat.models import CombatOpponent, CreatureTemplate
from world.combat.services import check_and_advance_boss_phase


class ReinforcementTests(TestCase):
    def test_phase_transition_spawns_reinforcements(self):
        encounter = CombatEncounterFactory()
        pool = ThreatPoolFactory()
        add_template = CreatureTemplate.objects.create(
            name="Add",
            tier=OpponentTier.MOOK,
            threat_pool=pool,
        )
        opp = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.BOSS,
            max_health=100,
            health=100,
            current_phase=1,
        )
        BossPhaseFactory(
            opponent=opp,
            phase_number=2,
            health_trigger_percentage=0.67,
            reinforcement_template=add_template,
            reinforcement_count=2,
        )
        opp.health = 66
        opp.save(update_fields=["health"])

        check_and_advance_boss_phase(opp)

        adds = CombatOpponent.objects.filter(
            encounter=encounter,
            tier=OpponentTier.MOOK,
        )
        self.assertEqual(adds.count(), 2)
        encounter = CombatEncounterFactory()
        opp = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.BOSS,
            max_health=100,
            health=100,
            current_phase=1,
        )
        BossPhaseFactory(
            opponent=opp,
            phase_number=2,
            health_trigger_percentage=0.67,
            reinforcement_count=0,
        )
        opp.health = 66
        opp.save(update_fields=["health"])

        check_and_advance_boss_phase(opp)

        self.assertEqual(CombatOpponent.objects.filter(encounter=encounter).count(), 1)


class BreakBarPhaseResetTests(TestCase):
    def test_phase_transition_resets_break_bar(self):
        """When a boss transitions to a new phase, the break bar recharges
        from the new phase's break-bar config."""
        encounter = CombatEncounterFactory()
        opp = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.BOSS,
            max_health=100,
            health=100,
            current_phase=1,
            break_bar_threshold=30,
            break_bar_current=10,
            vulnerability_rounds=2,
            vulnerability_intensity_bonus=2,
        )
        BossPhaseFactory(
            opponent=opp,
            phase_number=2,
            health_trigger_percentage=0.5,
            soak_value=10,
            break_bar_threshold=40,
            vulnerability_rounds=3,
            vulnerability_intensity_bonus=3,
        )
        # Damage the bar
        opp.break_bar_current = 10
        opp.save(update_fields=["break_bar_current"])
        # Trigger phase 2
        opp.health = 49
        opp.save(update_fields=["health"])
        check_and_advance_boss_phase(opp)
        opp.refresh_from_db()
        # Bar recharged from phase 2 config
        self.assertEqual(opp.break_bar_current, 40)
        self.assertEqual(opp.break_bar_threshold, 40)
        self.assertEqual(opp.vulnerability_rounds, 3)
        self.assertEqual(opp.vulnerability_intensity_bonus, 3)
        self.assertEqual(opp.vulnerability_rounds_remaining, 0)

    def test_phase_with_no_break_bar_clears_it(self):
        """Transitioning to a phase with no break bar (threshold=0) clears it."""
        encounter = CombatEncounterFactory()
        opp = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.BOSS,
            max_health=100,
            health=100,
            current_phase=1,
            break_bar_threshold=30,
            break_bar_current=15,
            vulnerability_rounds_remaining=1,
        )
        BossPhaseFactory(
            opponent=opp,
            phase_number=2,
            health_trigger_percentage=0.5,
            break_bar_threshold=0,
        )
        opp.health = 49
        opp.save(update_fields=["health"])
        check_and_advance_boss_phase(opp)
        opp.refresh_from_db()
        self.assertEqual(opp.break_bar_threshold, 0)
        self.assertEqual(opp.break_bar_current, 0)
        self.assertEqual(opp.vulnerability_rounds_remaining, 0)
