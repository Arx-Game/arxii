from django.core.exceptions import ValidationError
from django.test import TestCase

from world.covenants.constants import BattleBinding, CovenantType
from world.covenants.factories import CovenantFactory


class BattleCovenantModelTests(TestCase):
    def test_battle_covenant_requires_binding(self):
        cov = CovenantFactory.build(
            covenant_type=CovenantType.BATTLE, battle_binding="", sworn_objective="x"
        )
        with self.assertRaises(ValidationError):
            cov.clean()

    def test_durance_covenant_forbids_binding(self):
        cov = CovenantFactory.build(
            covenant_type=CovenantType.DURANCE,
            battle_binding=BattleBinding.STANDING,
            sworn_objective="x",
        )
        with self.assertRaises(ValidationError):
            cov.clean()

    def test_durance_covenant_forbids_dormant(self):
        cov = CovenantFactory.build(
            covenant_type=CovenantType.DURANCE, is_dormant=True, sworn_objective="x"
        )
        with self.assertRaises(ValidationError):
            cov.clean()

    def test_campaign_covenant_cannot_be_dormant(self):
        cov = CovenantFactory.build(
            covenant_type=CovenantType.BATTLE,
            battle_binding=BattleBinding.CAMPAIGN,
            is_dormant=True,
            sworn_objective="x",
        )
        with self.assertRaises(ValidationError):
            cov.clean()

    def test_valid_standing_battle_covenant_passes(self):
        cov = CovenantFactory.build(
            covenant_type=CovenantType.BATTLE,
            battle_binding=BattleBinding.STANDING,
            is_dormant=True,
            sworn_objective="x",
        )
        cov.clean()  # must not raise

    def test_create_covenant_persists_battle_binding(self):
        from world.character_sheets.factories import CharacterSheetFactory
        from world.covenants.factories import CovenantRoleFactory
        from world.covenants.services import create_covenant
        from world.covenants.types import CovenantFounder

        role = CovenantRoleFactory(covenant_type=CovenantType.BATTLE)
        founders = [
            CovenantFounder(character_sheet=CharacterSheetFactory(), role=role),
            CovenantFounder(character_sheet=CharacterSheetFactory(), role=role),
        ]
        cov = create_covenant(
            name="The Khati Crusade",
            covenant_type=CovenantType.BATTLE,
            sworn_objective="Free the Khati.",
            founders=founders,
            battle_binding=BattleBinding.CAMPAIGN,
        )
        self.assertEqual(cov.battle_binding, BattleBinding.CAMPAIGN)
        self.assertFalse(cov.is_dormant)

    def test_create_covenant_rejects_battle_without_binding(self):
        from world.character_sheets.factories import CharacterSheetFactory
        from world.covenants.exceptions import BattleBindingRequiredError
        from world.covenants.factories import CovenantRoleFactory
        from world.covenants.services import create_covenant
        from world.covenants.types import CovenantFounder

        role = CovenantRoleFactory(covenant_type=CovenantType.BATTLE)
        founders = [
            CovenantFounder(character_sheet=CharacterSheetFactory(), role=role),
            CovenantFounder(character_sheet=CharacterSheetFactory(), role=role),
        ]
        with self.assertRaises(BattleBindingRequiredError):
            create_covenant(
                name="Bindingless Battle",
                covenant_type=CovenantType.BATTLE,
                sworn_objective="x",
                founders=founders,
                battle_binding="",
            )

    def test_create_covenant_rejects_durance_with_binding(self):
        from world.character_sheets.factories import CharacterSheetFactory
        from world.covenants.exceptions import BattleBindingNotAllowedError
        from world.covenants.factories import CovenantRoleFactory
        from world.covenants.services import create_covenant
        from world.covenants.types import CovenantFounder

        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        founders = [
            CovenantFounder(character_sheet=CharacterSheetFactory(), role=role),
            CovenantFounder(character_sheet=CharacterSheetFactory(), role=role),
        ]
        with self.assertRaises(BattleBindingNotAllowedError):
            create_covenant(
                name="Bound Durance",
                covenant_type=CovenantType.DURANCE,
                sworn_objective="x",
                founders=founders,
                battle_binding=BattleBinding.STANDING,
            )
