"""Tests for opponent-side DAMAGE_PRE_APPLY emission.

Mirrors the participant-path tests in test_reactive_integration.py but for
apply_damage_to_opponent so reactive defences (force-field/reflect/blink) fire
identically on NPCs and ALLY summons. (#1584)
"""

from django.test import TestCase, tag

from world.combat.constants import OpponentTier
from world.combat.factories import CombatEncounterFactory, CombatOpponentFactory
from world.combat.services import apply_damage_to_opponent
from world.conditions.factories import install_cancel_damage_trigger


@tag("postgres")
class OpponentDamagePreApplyTests(TestCase):
    """apply_damage_to_opponent emits DAMAGE_PRE_APPLY; cancellation zeroes damage."""

    def test_cancelled_pre_apply_zeroes_damage(self) -> None:
        """A CANCEL_EVENT trigger on opp.objectdb prevents health loss."""
        enc = CombatEncounterFactory()
        opp = CombatOpponentFactory(
            encounter=enc,
            tier=OpponentTier.MOOK,
            health=50,
            max_health=50,
            soak_value=0,
        )
        install_cancel_damage_trigger(opp.objectdb)
        result = apply_damage_to_opponent(opp, 30)
        opp.refresh_from_db()
        self.assertEqual(result.damage_dealt, 0)
        self.assertEqual(opp.health, 50)

    def test_uncancelled_damage_still_lands(self) -> None:
        """Without a cancel trigger, damage is applied normally."""
        enc = CombatEncounterFactory()
        opp = CombatOpponentFactory(
            encounter=enc,
            tier=OpponentTier.MOOK,
            health=50,
            max_health=50,
            soak_value=0,
        )
        result = apply_damage_to_opponent(opp, 30)
        opp.refresh_from_db()
        self.assertEqual(result.damage_dealt, 30)
        self.assertEqual(opp.health, 20)
