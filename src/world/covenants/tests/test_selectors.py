"""Tests for world.covenants.selectors — shared actor-membership selectors."""

from django.test import TestCase

from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRankFactory,
)
from world.covenants.selectors import get_active_memberships, resolve_actor_membership


class ResolveActorMembershipTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.covenant = CovenantFactory()
        cls.manager_rank = CovenantRankFactory(
            covenant=cls.covenant, tier=1, can_manage_ranks=True, can_kick=True
        )
        cls.grunt_rank = CovenantRankFactory(covenant=cls.covenant, tier=2)
        cls.manager = CharacterCovenantRoleFactory(covenant=cls.covenant, rank=cls.manager_rank)
        cls.grunt = CharacterCovenantRoleFactory(covenant=cls.covenant, rank=cls.grunt_rank)

    def test_capability_filter_returns_manager(self):
        actor = resolve_actor_membership(
            covenant=self.covenant,
            character_sheets=[self.manager.character_sheet],
            capability="can_manage_ranks",
        )
        self.assertEqual(actor, self.manager)

    def test_capability_filter_excludes_grunt(self):
        actor = resolve_actor_membership(
            covenant=self.covenant,
            character_sheets=[self.grunt.character_sheet],
            capability="can_manage_ranks",
        )
        self.assertIsNone(actor)

    def test_get_active_memberships_lists_only_active(self):
        memberships = get_active_memberships(character_sheet=self.manager.character_sheet)
        self.assertIn(self.manager, memberships)
