from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.constants import BattleBinding, CovenantType
from world.covenants.factories import CovenantFactory, CovenantRoleFactory, make_engaged_member
from world.covenants.services import precedence_role_for_combat


class PrecedenceRoleTests(TestCase):
    def setUp(self):
        self.sheet = CharacterSheetFactory()
        durance_cov = CovenantFactory(covenant_type=CovenantType.DURANCE)
        self.durance_role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE, speed_rank=5)
        make_engaged_member(
            character_sheet=self.sheet, covenant=durance_cov, covenant_role=self.durance_role
        )
        battle_cov = CovenantFactory(
            covenant_type=CovenantType.BATTLE, battle_binding=BattleBinding.STANDING
        )
        self.battle_role = CovenantRoleFactory(covenant_type=CovenantType.BATTLE, speed_rank=2)
        make_engaged_member(
            character_sheet=self.sheet, covenant=battle_cov, covenant_role=self.battle_role
        )

    def test_battle_role_wins(self):
        self.sheet.character.covenant_roles.invalidate()
        self.assertEqual(precedence_role_for_combat(self.sheet), self.battle_role)

    def test_durance_only_returns_durance(self):
        sheet = CharacterSheetFactory()
        cov = CovenantFactory(covenant_type=CovenantType.DURANCE)
        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        make_engaged_member(character_sheet=sheet, covenant=cov, covenant_role=role)
        sheet.character.covenant_roles.invalidate()
        self.assertEqual(precedence_role_for_combat(sheet), role)

    def test_no_engaged_roles_returns_none(self):
        self.assertIsNone(precedence_role_for_combat(CharacterSheetFactory()))
