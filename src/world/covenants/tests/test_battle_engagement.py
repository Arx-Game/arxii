from django.test import TestCase

from world.covenants.constants import BattleBinding, CovenantType
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
)
from world.covenants.handlers import can_engage_membership


class BattleEngagementGateTests(TestCase):
    def _battle_membership(self, *, dormant: bool):
        cov = CovenantFactory(
            covenant_type=CovenantType.BATTLE,
            battle_binding=BattleBinding.STANDING,
            is_dormant=dormant,
        )
        role = CovenantRoleFactory(covenant_type=CovenantType.BATTLE)
        return CharacterCovenantRoleFactory(covenant=cov, covenant_role=role)

    def test_risen_battle_covenant_is_engageable(self):
        membership = self._battle_membership(dormant=False)
        self.assertTrue(can_engage_membership(membership))

    def test_dormant_battle_covenant_blocks_engagement(self):
        membership = self._battle_membership(dormant=True)
        self.assertFalse(can_engage_membership(membership))
