"""Tests for covenant Actions (#1346).

The happy-path engage is covered by the E2E journey test
``test_covenant_telnet_e2e.py`` (``CovenantMembershipRankStanddownTests.test_engage``).
These tests retain only the edge cases the journey does NOT cover: engaging a
dormant covenant, and kicking a member of equal or higher rank.
"""

from django.test import TestCase

from actions.definitions.covenants import (
    EngageCovenantMembershipAction,
    KickCovenantMemberAction,
)
from world.covenants.constants import BattleBinding, CovenantType
from world.covenants.exceptions import (
    CannotKickEqualOrHigherRankError,
    CovenantEngagementPrerequisiteNotMetError,
)
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRankFactory,
    CovenantRoleFactory,
)


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
