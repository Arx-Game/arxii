"""Tests for the smooth execute damage ramp (#2643).

``execute_missing_health_multiplier`` scales a hit's damage up as the target's
PRE-hit health runs low: ``factor = 1 + multiplier * missing_health_fraction``.
Default 0 on every damage profile is a byte-identical no-op — proven by the
existing (untouched) damage tests continuing to pass unmodified.
"""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from world.combat.factories import CombatOpponentFactory, CombatParticipantFactory
from world.combat.services import apply_damage_to_opponent, apply_damage_to_participant
from world.vitals.factories import CharacterVitalsFactory


class OpponentExecuteTests(TestCase):
    """Execute factor math at the opponent damage seam, priced off PRE-hit health."""

    def test_zero_multiplier_is_a_no_op(self):
        opponent = CombatOpponentFactory(health=50, max_health=100, soak_value=0)

        result = apply_damage_to_opponent(
            opponent, 100, execute_missing_health_multiplier=Decimal(0)
        )

        self.assertEqual(result.damage_dealt, 100)

    def test_half_health_multiplier_scales_damage(self):
        """50% missing health * multiplier 1.0 -> factor 1.5."""
        opponent = CombatOpponentFactory(health=50, max_health=100, soak_value=0)

        result = apply_damage_to_opponent(
            opponent, 100, execute_missing_health_multiplier=Decimal("1.0")
        )

        # missing_health_fraction = 1 - 50/100 = 0.5; factor = 1 + 1.0*0.5 = 1.5
        self.assertEqual(result.damage_dealt, 150)

    def test_full_health_target_gets_no_execute_bonus(self):
        """At full health, missing_health_fraction is 0 -> factor 1 (no change)."""
        opponent = CombatOpponentFactory(health=100, max_health=100, soak_value=0)

        result = apply_damage_to_opponent(
            opponent, 100, execute_missing_health_multiplier=Decimal("2.0")
        )

        self.assertEqual(result.damage_dealt, 100)

    def test_second_hit_prices_off_health_left_by_the_first_hit(self):
        """Two sequential hits: the second hit's execute basis is the health the
        FIRST hit left behind — pre-hit for THAT hit, never a recursive self-reference."""
        opponent = CombatOpponentFactory(health=100, max_health=100, soak_value=0)

        # First hit: full health -> no execute bonus. 100 -> health drops to 0? No,
        # use a smaller hit so health remains positive for a meaningful second hit.
        first = apply_damage_to_opponent(
            opponent, 20, execute_missing_health_multiplier=Decimal("1.0")
        )
        self.assertEqual(first.damage_dealt, 20)  # full health, no bonus
        opponent.refresh_from_db()
        self.assertEqual(opponent.health, 80)

        # Second hit: opponent is now at 80/100 health (20% missing).
        # factor = 1 + 1.0*0.2 = 1.2 -> 20 * 1.2 = 24
        second = apply_damage_to_opponent(
            opponent, 20, execute_missing_health_multiplier=Decimal("1.0")
        )
        self.assertEqual(second.damage_dealt, 24)


class ParticipantExecuteTests(TestCase):
    """Symmetric execute factor math at the participant damage seam.

    No live caller passes a nonzero multiplier yet (combat technique damage only
    ever resolves against CombatOpponent targets in this codebase) — tested
    directly so the capability is proven and ready for future PC-vs-PC wiring.
    """

    def _participant_with_vitals(self, *, health, max_health):
        participant = CombatParticipantFactory()
        CharacterVitalsFactory(
            character_sheet=participant.character_sheet,
            health=health,
            max_health=max_health,
            base_max_health=max_health,
        )
        return participant

    def test_zero_multiplier_is_a_no_op(self):
        participant = self._participant_with_vitals(health=50, max_health=100)

        result = apply_damage_to_participant(
            participant, 100, execute_missing_health_multiplier=Decimal(0)
        )

        self.assertEqual(result.damage_dealt, 100)

    def test_half_health_multiplier_scales_damage(self):
        participant = self._participant_with_vitals(health=50, max_health=100)

        result = apply_damage_to_participant(
            participant, 100, execute_missing_health_multiplier=Decimal("1.0")
        )

        self.assertEqual(result.damage_dealt, 150)

    def test_second_hit_prices_off_health_left_by_the_first_hit(self):
        participant = self._participant_with_vitals(health=100, max_health=100)

        first = apply_damage_to_participant(
            participant, 20, execute_missing_health_multiplier=Decimal("1.0")
        )
        self.assertEqual(first.damage_dealt, 20)

        second = apply_damage_to_participant(
            participant, 20, execute_missing_health_multiplier=Decimal("1.0")
        )
        # Health is now 80/100 (20% missing): factor = 1 + 1.0*0.2 = 1.2 -> 24
        self.assertEqual(second.damage_dealt, 24)
