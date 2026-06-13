from django.test import TestCase

from world.combat.factories import CombatEncounterFactory, CombatOpponentFactory
from world.combat.services import increment_probing


class IncrementProbingTest(TestCase):
    def setUp(self):
        self.encounter = CombatEncounterFactory()
        self.opponent = CombatOpponentFactory(encounter=self.encounter, probing_current=2)

    def test_adds_amount_and_persists(self):
        increment_probing(self.opponent, 3)
        self.opponent.refresh_from_db()
        self.assertEqual(self.opponent.probing_current, 5)

    def test_clamps_at_zero(self):
        increment_probing(self.opponent, -10)
        self.opponent.refresh_from_db()
        self.assertEqual(self.opponent.probing_current, 0)
