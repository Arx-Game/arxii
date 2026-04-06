"""Tests for combat damage resolution service functions."""

from django.test import TestCase

from world.combat.constants import OpponentStatus, ParticipantStatus
from world.combat.factories import (
    BossOpponentFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.services import apply_damage_to_opponent, apply_damage_to_participant


class ApplyDamageToOpponentTest(TestCase):
    """Tests for apply_damage_to_opponent."""

    def test_damage_reduces_health(self) -> None:
        opponent = CombatOpponentFactory(health=50, max_health=50)
        result = apply_damage_to_opponent(opponent, 20)

        opponent.refresh_from_db()
        self.assertEqual(opponent.health, 30)
        self.assertEqual(result.damage_dealt, 20)
        self.assertTrue(result.health_damaged)
        self.assertFalse(result.defeated)

    def test_damage_below_soak_still_probes(self) -> None:
        opponent = BossOpponentFactory(health=500, max_health=500, soak_value=80)
        result = apply_damage_to_opponent(opponent, 30)

        opponent.refresh_from_db()
        self.assertEqual(opponent.health, 500)
        self.assertEqual(result.damage_dealt, 0)
        self.assertFalse(result.health_damaged)
        self.assertTrue(result.probed)
        self.assertEqual(result.probing_increment, 30)

    def test_damage_above_soak_applies_and_probes(self) -> None:
        opponent = BossOpponentFactory(health=500, max_health=500, soak_value=80)
        result = apply_damage_to_opponent(opponent, 100)

        opponent.refresh_from_db()
        self.assertEqual(opponent.health, 480)
        self.assertEqual(result.damage_dealt, 20)
        self.assertTrue(result.health_damaged)
        self.assertTrue(result.probed)
        self.assertEqual(result.probing_increment, 100)

    def test_zero_health_defeats_opponent(self) -> None:
        opponent = CombatOpponentFactory(health=10, max_health=50)
        result = apply_damage_to_opponent(opponent, 15)

        opponent.refresh_from_db()
        self.assertEqual(opponent.health, -5)
        self.assertEqual(opponent.status, OpponentStatus.DEFEATED)
        self.assertTrue(result.defeated)

    def test_combo_damage_bypasses_soak(self) -> None:
        opponent = BossOpponentFactory(health=500, max_health=500, soak_value=80)
        probing_before = opponent.probing_current
        result = apply_damage_to_opponent(opponent, 50, bypass_soak=True)

        opponent.refresh_from_db()
        self.assertEqual(opponent.health, 450)
        self.assertEqual(result.damage_dealt, 50)
        self.assertTrue(result.health_damaged)
        # Combo damage should not probe — probing_current unchanged
        self.assertEqual(opponent.probing_current, probing_before)
        self.assertFalse(result.probed)
        self.assertEqual(result.probing_increment, 0)

    def test_probing_increment_equals_raw_damage(self) -> None:
        opponent = BossOpponentFactory(health=500, max_health=500, soak_value=80)

        result_soaked = apply_damage_to_opponent(opponent, 30)
        self.assertEqual(result_soaked.probing_increment, 30)

        opponent.refresh_from_db()
        result_through = apply_damage_to_opponent(opponent, 100)
        self.assertEqual(result_through.probing_increment, 100)


class ApplyDamageToParticipantTest(TestCase):
    """Tests for apply_damage_to_participant."""

    def test_damage_reduces_health(self) -> None:
        participant = CombatParticipantFactory(health=100, max_health=100)
        result = apply_damage_to_participant(participant, 30)

        participant.refresh_from_db()
        self.assertEqual(participant.health, 70)
        self.assertEqual(result.health_after, 70)
        self.assertEqual(result.damage_dealt, 30)

    def test_health_can_go_negative(self) -> None:
        participant = CombatParticipantFactory(health=10, max_health=100)
        result = apply_damage_to_participant(participant, 25)

        participant.refresh_from_db()
        self.assertEqual(participant.health, -15)
        self.assertEqual(result.health_after, -15)

    def test_knockout_eligible_below_20_percent(self) -> None:
        participant = CombatParticipantFactory(health=15, max_health=100)
        result = apply_damage_to_participant(participant, 5)

        self.assertEqual(result.health_after, 10)
        self.assertTrue(result.knockout_eligible)
        self.assertFalse(result.death_eligible)

    def test_not_knockout_eligible_above_20_percent(self) -> None:
        participant = CombatParticipantFactory(health=100, max_health=100)
        result = apply_damage_to_participant(participant, 10)

        self.assertEqual(result.health_after, 90)
        self.assertFalse(result.knockout_eligible)

    def test_death_eligible_at_zero(self) -> None:
        participant = CombatParticipantFactory(health=5, max_health=100)
        result = apply_damage_to_participant(participant, 10)

        self.assertEqual(result.health_after, -5)
        self.assertTrue(result.death_eligible)

    def test_permanent_wound_on_big_hit(self) -> None:
        participant = CombatParticipantFactory(health=100, max_health=100)
        result = apply_damage_to_participant(participant, 60)

        self.assertTrue(result.permanent_wound_eligible)

    def test_no_permanent_wound_on_small_hit(self) -> None:
        participant = CombatParticipantFactory(health=100, max_health=100)
        result = apply_damage_to_participant(participant, 30)

        self.assertFalse(result.permanent_wound_eligible)

    def test_force_death_sets_dying(self) -> None:
        participant = CombatParticipantFactory(health=50, max_health=100)
        result = apply_damage_to_participant(participant, 10, force_death=True)

        participant.refresh_from_db()
        self.assertEqual(participant.status, ParticipantStatus.DYING)
        self.assertTrue(participant.dying_final_round)
        self.assertEqual(result.health_after, 40)
