"""Tests for covenant Actions (#1346).

The happy-path engage is covered by the E2E journey test
``test_covenant_telnet_e2e.py`` (``CovenantMembershipRankStanddownTests.test_engage``).
These tests retain only the edge cases the journey does NOT cover: engaging a
dormant covenant, and kicking a member of equal or higher rank.
"""

from django.test import TestCase

from actions.definitions.covenants import (
    DepositCovenantFundsAction,
    EngageCovenantMembershipAction,
    KickCovenantMemberAction,
    WithdrawCovenantFundsAction,
)
from world.covenants.constants import BattleBinding, CovenantType
from world.covenants.exceptions import (
    CannotKickEqualOrHigherRankError,
    CovenantEngagementPrerequisiteNotMetError,
    NotAuthorizedToSpendCovenantTreasuryError,
)
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRankFactory,
    CovenantRoleFactory,
)
from world.covenants.treasury import covenant_treasury
from world.currency.services import get_or_create_purse


class CovenantActionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Use a risen (non-dormant) BATTLE covenant so can_engage_membership passes.
        cls.covenant = CovenantFactory(
            covenant_type=CovenantType.BATTLE,
            battle_binding=BattleBinding.STANDING,
            is_dormant=False,
        )
        cls.role = CovenantRoleFactory(covenant_type=CovenantType.BATTLE)
        cls.top = CovenantRankFactory(covenant=cls.covenant, tier=1, can_kick=True)
        cls.officer = CharacterCovenantRoleFactory(
            covenant=cls.covenant, covenant_role=cls.role, rank=cls.top
        )

    def test_engage_dormant_battle_covenant_fails(self):
        """Engaging a dormant BATTLE covenant returns failure — gate protects the rise ceremony."""
        dormant_covenant = CovenantFactory(
            covenant_type=CovenantType.BATTLE,
            battle_binding=BattleBinding.STANDING,
            is_dormant=True,
        )
        dormant_role = CovenantRoleFactory(covenant_type=CovenantType.BATTLE)
        dormant_membership = CharacterCovenantRoleFactory(
            covenant=dormant_covenant, covenant_role=dormant_role
        )

        result = EngageCovenantMembershipAction().run(
            actor=dormant_membership.character_sheet.character,
            membership=dormant_membership,
        )
        self.assertFalse(result.success)
        self.assertEqual(result.message, CovenantEngagementPrerequisiteNotMetError.user_message)

    def test_kick_equal_rank_surfaces_user_message(self):
        peer = CharacterCovenantRoleFactory(covenant=self.covenant, rank=self.top)
        result = KickCovenantMemberAction().run(
            actor=self.officer.character_sheet.character,
            target=peer,
            actor_membership=self.officer,
        )
        self.assertFalse(result.success)
        self.assertEqual(result.message, CannotKickEqualOrHigherRankError().user_message)

    def test_deposit_action_moves_purse_to_treasury(self):
        purse = get_or_create_purse(self.officer.character_sheet)
        purse.balance = 100
        purse.save(update_fields=["balance"])

        result = DepositCovenantFundsAction().run(
            actor=self.officer.character_sheet.character,
            membership=self.officer,
            amount=40,
        )
        self.assertTrue(result.success)
        treasury = covenant_treasury(self.covenant)
        self.assertEqual(treasury.balance, 40)

    def test_withdraw_action_surfaces_rank_error(self):
        base_rank = CovenantRankFactory(covenant=self.covenant, tier=2)
        base_member = CharacterCovenantRoleFactory(covenant=self.covenant, rank=base_rank)

        result = WithdrawCovenantFundsAction().run(
            actor=base_member.character_sheet.character,
            membership=base_member,
            amount=10,
        )
        self.assertFalse(result.success)
        self.assertEqual(result.message, NotAuthorizedToSpendCovenantTreasuryError.user_message)
