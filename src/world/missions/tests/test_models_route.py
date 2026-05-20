"""Tests for MissionOptionRoute + MissionOptionRouteCandidate (Task 2.3).

A CHECK option routes per resolved outcome tier; a BRANCH option has a
single null-tier route. A route may be terminal (null target_node) or a
randomized set drawn from weighted candidates.
"""

from django.test import TestCase

from world.checks.factories import CheckTypeFactory
from world.missions.constants import OptionKind, OptionSource
from world.missions.factories import (
    MissionNodeFactory,
    MissionOptionFactory,
    MissionOptionRouteCandidateFactory,
    MissionOptionRouteFactory,
    MissionTemplateFactory,
)
from world.missions.models import MissionOptionRoute
from world.traits.factories import CheckOutcomeFactory


class MissionOptionRouteTests(TestCase):
    """Per-tier routing, BRANCH single route, terminal + randomized sets."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.template = MissionTemplateFactory(slug="route-tmpl")
        cls.entry = MissionNodeFactory(template=cls.template, key="entry", is_entry=True)
        cls.node_a = MissionNodeFactory(template=cls.template, key="a")
        cls.node_b = MissionNodeFactory(template=cls.template, key="b")
        cls.success = CheckOutcomeFactory(name="Success")
        cls.failure = CheckOutcomeFactory(name="Failure")
        cls.sneak = CheckTypeFactory(name="Sneak")
        cls.check_option = MissionOptionFactory(
            node=cls.entry,
            order=0,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.AUTHORED,
            authored_check_type=cls.sneak,
        )
        cls.branch_option = MissionOptionFactory(
            node=cls.entry,
            order=1,
            option_kind=OptionKind.BRANCH,
            source_kind=OptionSource.AUTHORED,
        )

    def test_check_option_success_and_fail_routes(self) -> None:
        success_route = MissionOptionRouteFactory(
            option=self.check_option,
            outcome_tier=self.success,
            target_node=self.node_a,
        )
        fail_route = MissionOptionRouteFactory(
            option=self.check_option,
            outcome_tier=self.failure,
            target_node=self.node_b,
        )
        routes = MissionOptionRoute.objects.filter(option=self.check_option)
        self.assertEqual(routes.count(), 2)
        self.assertEqual(success_route.target_node, self.node_a)
        self.assertEqual(fail_route.target_node, self.node_b)

    def test_branch_option_single_null_tier_route(self) -> None:
        route = MissionOptionRouteFactory(
            option=self.branch_option,
            outcome_tier=None,
            target_node=self.node_a,
        )
        self.assertIsNone(route.outcome_tier)
        self.assertEqual(route.target_node, self.node_a)
        self.assertEqual(str(route), f"{self.branch_option} [branch]")

    def test_terminal_route_allows_null_target_node(self) -> None:
        route = MissionOptionRouteFactory(
            option=self.branch_option,
            outcome_tier=None,
            target_node=None,
        )
        self.assertIsNone(route.target_node)

    def test_randomized_success_set_of_two_candidates(self) -> None:
        route = MissionOptionRouteFactory(
            option=self.check_option,
            outcome_tier=self.success,
            target_node=None,
            is_random_set=True,
        )
        c1 = MissionOptionRouteCandidateFactory(
            route=route,
            target_node=self.node_a,
            weight=3,
        )
        c2 = MissionOptionRouteCandidateFactory(
            route=route,
            target_node=self.node_b,
            weight=1,
        )
        self.assertTrue(route.is_random_set)
        self.assertEqual(route.candidates.count(), 2)
        self.assertEqual(c1.weight, 3)
        self.assertEqual(c2.weight, 1)
