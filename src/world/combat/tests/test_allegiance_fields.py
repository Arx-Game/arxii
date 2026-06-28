from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import CombatAllegiance
from world.combat.factories import CombatOpponentFactory


class AllegianceFieldsTests(TestCase):
    def test_opponent_defaults_to_enemy_with_no_summoner(self):
        opp = CombatOpponentFactory()
        self.assertEqual(opp.allegiance, CombatAllegiance.ENEMY)
        self.assertIsNone(opp.summoned_by)
        self.assertIsNone(opp.bond_expires_round)

    def test_opponent_can_be_an_ally_summon(self):
        sheet = CharacterSheetFactory()
        opp = CombatOpponentFactory(
            allegiance=CombatAllegiance.ALLY, summoned_by=sheet, bond_expires_round=5
        )
        opp.refresh_from_db()
        self.assertEqual(opp.allegiance, CombatAllegiance.ALLY)
        self.assertEqual(opp.summoned_by, sheet)
        self.assertEqual(opp.bond_expires_round, 5)
