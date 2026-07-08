"""Tests for party-NPC morale model + state helper (#2015)."""

from django.test import TestCase

from world.combat.constants import (
    BREAK_MORALE_THRESHOLD,
    DEFAULT_OPPONENT_MORALE,
    DEMORALIZE_MORALE_PER_LEVEL,
    FALTER_MORALE_THRESHOLD,
    MINDLESS_MORALE_RESISTANCE,
    PARLEY_DISPOSITION_FLOOR,
    RALLY_BASE_DIFFICULTY,
    RALLY_MORALE_PER_LEVEL,
    TAUNT_THREAT_PER_LEVEL,
    CombatManeuver,
)
from world.combat.factories import CombatOpponentFactory, OpponentTierTemplateFactory


class MoraleConstantsTests(TestCase):
    def test_morale_threshold_constants_exist(self) -> None:
        self.assertEqual(DEFAULT_OPPONENT_MORALE, 70)
        self.assertEqual(FALTER_MORALE_THRESHOLD, 50)
        self.assertEqual(BREAK_MORALE_THRESHOLD, 25)
        self.assertEqual(DEMORALIZE_MORALE_PER_LEVEL, 15)
        self.assertEqual(RALLY_MORALE_PER_LEVEL, 15)
        self.assertEqual(TAUNT_THREAT_PER_LEVEL, 25)
        self.assertEqual(RALLY_BASE_DIFFICULTY, 10)
        self.assertEqual(PARLEY_DISPOSITION_FLOOR, 20)
        self.assertEqual(MINDLESS_MORALE_RESISTANCE, 30)

    def test_new_maneuver_enum_values(self) -> None:
        self.assertEqual(CombatManeuver.RALLY, "rally")
        self.assertEqual(CombatManeuver.DEMORALIZE, "demoralize")
        self.assertEqual(CombatManeuver.TAUNT, "taunt")
        self.assertEqual(CombatManeuver.PARLEY, "parley")


class CombatOpponentMoraleFieldTests(TestCase):
    def test_morale_defaults_to_constant(self) -> None:
        opp = CombatOpponentFactory()
        opp.refresh_from_db()
        self.assertEqual(opp.morale, DEFAULT_OPPONENT_MORALE)
        self.assertEqual(opp.max_morale, 100)

    def test_morale_can_be_overridden(self) -> None:
        opp = CombatOpponentFactory(morale=10)
        self.assertEqual(opp.morale, 10)


class OpponentTierTemplateHasMoraleTests(TestCase):
    def test_has_morale_defaults_true(self) -> None:
        tpl = OpponentTierTemplateFactory()
        self.assertTrue(tpl.has_morale)


class ThreatPoolEntryRequiresSteadyTests(TestCase):
    def test_requires_steady_defaults_false(self) -> None:
        from world.combat.factories import ThreatPoolEntryFactory

        entry = ThreatPoolEntryFactory()
        self.assertFalse(entry.requires_steady)
