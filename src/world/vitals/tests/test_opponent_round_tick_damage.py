"""Round-tick DoT damage reaches an NPC opponent, which has no vitals (#4572)."""

from __future__ import annotations

from django.test import TestCase
from evennia import create_object

from world.combat.constants import OpponentStatus
from world.combat.factories import CombatEncounterFactory, CombatOpponentFactory
from world.conditions.factories import (
    ConditionDamageOverTimeFactory,
    ConditionResistanceModifierFactory,
    ConditionTemplateFactory,
    DamageTypeFactory,
)
from world.conditions.services import apply_condition
from world.conditions.types import RoundTickResult
from world.vitals.services import _apply_round_tick_damage, tick_round_for_targets


class OpponentRoundTickDamageTests(TestCase):
    """A bleed/burn/poison on an opponent debits the CombatOpponent's health."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.fire = DamageTypeFactory(name="Opponent Tick Fire")
        cls.burning = ConditionTemplateFactory(name="Opponent Tick Burning")
        ConditionDamageOverTimeFactory(
            condition=cls.burning,
            damage_type=cls.fire,
            base_damage=6,
            scales_with_severity=False,
            scales_with_stacks=False,
        )
        cls.ward = ConditionTemplateFactory(name="Opponent Tick Fire Ward")
        ConditionResistanceModifierFactory(
            condition=cls.ward, damage_type=cls.fire, modifier_value=4
        )

    def setUp(self) -> None:
        # Built per test: the opponent's body caches its condition handler, so a
        # shared one would carry applied conditions across tests.
        self.encounter = CombatEncounterFactory()
        self.opponent = CombatOpponentFactory(encounter=self.encounter, health=50, max_health=50)
        self.body = self.opponent.objectdb

    def test_dot_condition_hurts_opponent_at_round_end(self) -> None:
        """A burning opponent loses the DoT's base damage through the round tick."""
        apply_condition(self.body, self.burning)
        tick_round_for_targets([self.body])
        self.opponent.refresh_from_db()
        self.assertEqual(self.opponent.health, 44)

    def test_dot_tick_ignores_armor_soak(self) -> None:
        """DoT skips armor soak, as PC DoT does."""
        self.opponent.soak_value = 100
        self.opponent.save(update_fields=["soak_value"])
        _apply_round_tick_damage(self.body, RoundTickResult(damage_dealt=[(self.fire, 6)]))
        self.opponent.refresh_from_db()
        self.assertEqual(self.opponent.health, 44)

    def test_dot_tick_does_not_probe(self) -> None:
        """A bleed is not a probing blow; it adds no probing progress."""
        _apply_round_tick_damage(self.body, RoundTickResult(damage_dealt=[(self.fire, 6)]))
        self.opponent.refresh_from_db()
        self.assertEqual(self.opponent.probing_current, 0)

    def test_resistance_condition_reduces_dot_once(self) -> None:
        """A fire-resistance condition nets once off the tick: 6 - 4 = 2."""
        apply_condition(self.body, self.ward)
        _apply_round_tick_damage(self.body, RoundTickResult(damage_dealt=[(self.fire, 6)]))
        self.opponent.refresh_from_db()
        self.assertEqual(self.opponent.health, 48)

    def test_multiple_damage_types_each_apply(self) -> None:
        """Every (damage_type, amount) pair in the tick lands."""
        acid = DamageTypeFactory(name="Opponent Tick Acid")
        result = RoundTickResult(damage_dealt=[(self.fire, 6), (acid, 3), (None, 0)])
        _apply_round_tick_damage(self.body, result)
        self.opponent.refresh_from_db()
        self.assertEqual(self.opponent.health, 41)

    def test_dot_that_reaches_zero_defeats_opponent(self) -> None:
        """Lethal DoT follows the hit path: the opponent is defeated."""
        self.opponent.health = 5
        self.opponent.save(update_fields=["health"])
        _apply_round_tick_damage(self.body, RoundTickResult(damage_dealt=[(self.fire, 6)]))
        self.opponent.refresh_from_db()
        self.assertEqual(self.opponent.status, OpponentStatus.DEFEATED)
        self.assertLessEqual(self.opponent.health, 0)

    def test_defeated_opponent_takes_no_further_damage(self) -> None:
        """Only an ACTIVE opponent is hurt by the tick."""
        self.opponent.status = OpponentStatus.DEFEATED
        self.opponent.save(update_fields=["status"])
        _apply_round_tick_damage(self.body, RoundTickResult(damage_dealt=[(self.fire, 6)]))
        self.opponent.refresh_from_db()
        self.assertEqual(self.opponent.health, 50)

    def test_object_that_is_not_an_opponent_is_a_noop(self) -> None:
        """A vase with a DoT and no CombatOpponent row is untouched and does not raise."""
        vase = create_object("typeclasses.objects.Object", key="vase", nohome=True)
        _apply_round_tick_damage(vase, RoundTickResult(damage_dealt=[(self.fire, 6)]))
        self.opponent.refresh_from_db()
        self.assertEqual(self.opponent.health, 50)
