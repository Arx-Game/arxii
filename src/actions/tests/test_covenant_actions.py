from django.test import TestCase

from actions.definitions.covenants import (
    EngageCovenantMembershipAction,
    KickCovenantMemberAction,
)
from world.covenants.exceptions import CannotKickEqualOrHigherRankError
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRankFactory,
)


class CovenantActionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.covenant = CovenantFactory()
        cls.top = CovenantRankFactory(covenant=cls.covenant, tier=1, can_kick=True)
        cls.low = CovenantRankFactory(covenant=cls.covenant, tier=2)
        cls.officer = CharacterCovenantRoleFactory(covenant=cls.covenant, rank=cls.top)
        cls.member = CharacterCovenantRoleFactory(covenant=cls.covenant, rank=cls.low)

    def test_engage_succeeds(self):
        result = EngageCovenantMembershipAction().run(
            actor=self.member.character_sheet.character, membership=self.member
        )
        self.member.refresh_from_db()
        self.assertTrue(result.success)
        self.assertTrue(self.member.engaged)

    def test_kick_equal_rank_surfaces_user_message(self):
        peer = CharacterCovenantRoleFactory(covenant=self.covenant, rank=self.top)
        result = KickCovenantMemberAction().run(
            actor=self.officer.character_sheet.character,
            target=peer,
            actor_membership=self.officer,
        )
        self.assertFalse(result.success)
        self.assertEqual(result.message, CannotKickEqualOrHigherRankError().user_message)
