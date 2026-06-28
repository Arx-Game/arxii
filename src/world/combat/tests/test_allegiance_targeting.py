from django.test import TestCase

from world.combat.constants import CombatAllegiance
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.services import combatants_hostile_to


class CombatantsHostileToTests(TestCase):
    def setUp(self):
        self.enc = CombatEncounterFactory()
        self.pc = CombatParticipantFactory(encounter=self.enc)
        self.enemy = CombatOpponentFactory(encounter=self.enc, allegiance=CombatAllegiance.ENEMY)
        self.ally = CombatOpponentFactory(encounter=self.enc, allegiance=CombatAllegiance.ALLY)

    def test_enemy_targets_pcs_and_ally_summons(self):
        targets = combatants_hostile_to(self.enemy)
        self.assertIn(self.pc, targets["participants"])
        self.assertIn(self.ally, targets["opponents"])

    def test_ally_summon_targets_enemy_opponents_only(self):
        targets = combatants_hostile_to(self.ally)
        self.assertEqual(targets["participants"], [])
        self.assertIn(self.enemy, targets["opponents"])
        self.assertNotIn(self.ally, targets["opponents"])
