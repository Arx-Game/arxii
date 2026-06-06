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
