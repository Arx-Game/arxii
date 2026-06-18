from django.test import TestCase

from world.combat.constants import CombatManeuver, DuelChallengeStatus, EncounterType, RiskLevel
from world.combat.factories import CombatEncounterFactory


class DuelEnumTests(TestCase):
    def test_duel_enum_members_exist(self):
        self.assertEqual(EncounterType.DUEL, "duel")
        self.assertEqual(CombatManeuver.YIELD, "yield")
        self.assertEqual(DuelChallengeStatus.PENDING, "pending")

    def test_is_lethal_derives_from_risk_level(self):
        lethal = CombatEncounterFactory(risk_level=RiskLevel.LETHAL)
        spar = CombatEncounterFactory(risk_level=RiskLevel.MODERATE)
        self.assertTrue(lethal.is_lethal)
        self.assertFalse(spar.is_lethal)
