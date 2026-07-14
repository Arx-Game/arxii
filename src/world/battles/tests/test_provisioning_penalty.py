"""Tests for provisioning penalties applied to battle units (#2375)."""

from django.test import TestCase

from world.agriculture.services.production import get_food_config
from world.battles.constants import DEFAULT_MORALE
from world.battles.factories import BattleFactory, BattleSideFactory
from world.battles.services import add_unit
from world.covenants.constants import BattleBinding, CovenantType
from world.covenants.factories import CovenantFactory


class ProvisioningPenaltyTests(TestCase):
    def setUp(self):
        self.battle = BattleFactory()
        self.config = get_food_config()
        self.config.max_provisioning_morale_penalty = 30
        self.config.max_provisioning_strength_penalty = 30
        self.config.save()

    def test_no_covenant_no_penalty(self):
        """Units on a side with no covenant are unaffected."""
        side = BattleSideFactory(battle=self.battle)  # covenant=None

        unit = add_unit(battle=self.battle, side=side, name="Test Unit")

        assert unit.military_unit.strength == 100
        assert unit.military_unit.morale == DEFAULT_MORALE

    def test_full_provisioning_no_penalty(self):
        """Units under a fully-provisioned covenant are unaffected."""
        covenant = CovenantFactory(
            covenant_type=CovenantType.BATTLE,
            battle_binding=BattleBinding.STANDING,
        )
        covenant.provisioning_ratio = 1.0
        covenant.save()
        side = BattleSideFactory(battle=self.battle, covenant=covenant)

        unit = add_unit(battle=self.battle, side=side, name="Test Unit")

        assert unit.military_unit.strength == 100
        assert unit.military_unit.morale == DEFAULT_MORALE

    def test_shortage_penalty(self):
        """Units under a poorly-provisioned covenant have reduced morale/strength."""
        covenant = CovenantFactory(
            covenant_type=CovenantType.BATTLE,
            battle_binding=BattleBinding.STANDING,
        )
        covenant.provisioning_ratio = 0.5  # 50% shortfall
        covenant.save()
        side = BattleSideFactory(battle=self.battle, covenant=covenant)

        unit = add_unit(battle=self.battle, side=side, name="Test Unit")

        # shortfall = 0.5, penalty = round(0.5 * 30) = 15
        assert unit.military_unit.strength == 100 - 15
        assert unit.military_unit.morale == DEFAULT_MORALE - 15

    def test_zero_provisioning_max_penalty(self):
        """Units under a covenant with zero provisioning get max penalty."""
        covenant = CovenantFactory(
            covenant_type=CovenantType.BATTLE,
            battle_binding=BattleBinding.STANDING,
        )
        covenant.provisioning_ratio = 0.0
        covenant.save()
        side = BattleSideFactory(battle=self.battle, covenant=covenant)

        unit = add_unit(battle=self.battle, side=side, name="Test Unit")

        assert unit.military_unit.strength == 100 - 30
        assert unit.military_unit.morale == DEFAULT_MORALE - 30

    def test_penalty_never_below_one(self):
        """Penalty never reduces morale/strength below 1."""
        self.config.max_provisioning_morale_penalty = 200
        self.config.max_provisioning_strength_penalty = 200
        self.config.save()

        covenant = CovenantFactory(
            covenant_type=CovenantType.BATTLE,
            battle_binding=BattleBinding.STANDING,
        )
        covenant.provisioning_ratio = 0.0
        covenant.save()
        side = BattleSideFactory(battle=self.battle, covenant=covenant)

        unit = add_unit(battle=self.battle, side=side, name="Test Unit", strength=50, morale=50)

        assert unit.military_unit.strength == 1
        assert unit.military_unit.morale == 1
