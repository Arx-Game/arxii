"""Tests for MissionOptionRoute + MissionOptionRouteCandidate (Task 2.3 + B4).

A CHECK option routes per resolved outcome tier; a BRANCH option has a
single null-tier route. A route may be terminal (null target_node) or a
randomized set drawn from weighted candidates. B4 enriches each candidate
with an optional per-candidate consequence + outcome_text override, and
makes MissionOptionRouteReward polymorphic on (route XOR candidate) so a
random-pool entry can carry its own reward bundle (design §8.3).
"""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.checks.factories import CheckTypeFactory, ConsequenceFactory
from world.missions.constants import DeedRewardKind, DeedRewardSink, OptionKind, OptionSource
from world.missions.factories import (
    MissionNodeFactory,
    MissionOptionFactory,
    MissionOptionRouteCandidateFactory,
    MissionOptionRouteFactory,
    MissionOptionRouteRewardFactory,
    MissionTemplateFactory,
)
from world.missions.models import MissionOptionRoute, MissionOptionRouteReward
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


class MissionOptionRouteCandidateEnrichmentTests(TestCase):
    """B4: per-candidate consequence + outcome_text override fields.

    Each candidate can optionally carry its OWN consequence and outcome
    text so a random-pool entry is a full self-contained outcome bundle
    (design §8.3). The new fields are STORED BUT UNCONSUMED in Phase B —
    Phase D wires per-candidate emission. Until then candidates with null
    consequence / blank outcome_text fall back to the parent route.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.template = MissionTemplateFactory(slug="cand-enrich-tmpl")
        cls.entry = MissionNodeFactory(template=cls.template, key="entry", is_entry=True)
        cls.dest = MissionNodeFactory(template=cls.template, key="dest")
        cls.option = MissionOptionFactory(
            node=cls.entry,
            order=0,
            option_kind=OptionKind.BRANCH,
            source_kind=OptionSource.AUTHORED,
        )
        cls.success = CheckOutcomeFactory(name="CandEnrichSuccess", success_level=2)
        cls.route = MissionOptionRouteFactory(
            option=cls.option,
            outcome_tier=cls.success,
            is_random_set=True,
        )

    def test_candidate_consequence_defaults_null(self) -> None:
        candidate = MissionOptionRouteCandidateFactory(route=self.route, target_node=self.dest)
        self.assertIsNone(candidate.consequence)

    def test_candidate_outcome_text_defaults_blank(self) -> None:
        candidate = MissionOptionRouteCandidateFactory(route=self.route, target_node=self.dest)
        self.assertEqual(candidate.outcome_text, "")

    def test_candidate_with_overrides_round_trips(self) -> None:
        consequence = ConsequenceFactory(label="Per-candidate effect")
        candidate = MissionOptionRouteCandidateFactory(
            route=self.route,
            target_node=self.dest,
            consequence=consequence,
            outcome_text="A specific outcome for this random branch.",
        )
        candidate.refresh_from_db()
        self.assertEqual(candidate.consequence, consequence)
        self.assertEqual(
            candidate.outcome_text,
            "A specific outcome for this random branch.",
        )


class MissionOptionRouteRewardParentTests(TestCase):
    """B4: a reward template hangs off EITHER a route OR a candidate (XOR).

    Per-candidate reward rows are STORED BUT UNCONSUMED in Phase B; Phase
    D's emit_terminal_rewards walks them when a random candidate fires.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.template = MissionTemplateFactory(slug="reward-parent-tmpl")
        cls.entry = MissionNodeFactory(template=cls.template, key="entry", is_entry=True)
        cls.option = MissionOptionFactory(
            node=cls.entry,
            order=0,
            option_kind=OptionKind.BRANCH,
            source_kind=OptionSource.AUTHORED,
        )
        cls.route = MissionOptionRouteFactory(option=cls.option, outcome_tier=None)
        cls.candidate = MissionOptionRouteCandidateFactory(
            route=cls.route,
            target_node=cls.entry,
        )

    def test_reward_on_route_round_trips(self) -> None:
        # Pre-existing path: reward hangs off the route, candidate null.
        reward = MissionOptionRouteRewardFactory(
            route=self.route,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.MONEY,
            amount=100,
        )
        self.assertEqual(reward.route, self.route)
        self.assertIsNone(reward.candidate)

    def test_reward_on_candidate_round_trips(self) -> None:
        # New path: reward hangs off a candidate, route null.
        reward = MissionOptionRouteReward.objects.create(
            route=None,
            candidate=self.candidate,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.LEGEND_POINTS,
            amount=50,
        )
        self.assertIsNone(reward.route)
        self.assertEqual(reward.candidate, self.candidate)

    def test_reward_requires_exactly_one_parent(self) -> None:
        # Neither route nor candidate set is invalid.
        with self.assertRaises(ValidationError):
            MissionOptionRouteReward.objects.create(
                route=None,
                candidate=None,
                kind=DeedRewardKind.IMMEDIATE,
                sink=DeedRewardSink.MONEY,
                amount=10,
            )

    def test_reward_cannot_have_both_parents(self) -> None:
        with self.assertRaises(ValidationError):
            MissionOptionRouteReward.objects.create(
                route=self.route,
                candidate=self.candidate,
                kind=DeedRewardKind.IMMEDIATE,
                sink=DeedRewardSink.MONEY,
                amount=10,
            )

    def test_candidate_cascade_deletes_its_rewards(self) -> None:
        MissionOptionRouteReward.objects.create(
            route=None,
            candidate=self.candidate,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.MONEY,
            amount=20,
        )
        self.candidate.delete()
        self.assertEqual(
            MissionOptionRouteReward.objects.filter(candidate=self.candidate.pk).count(),
            0,
        )


class MissionOptionRouteOutcomeTextTests(TestCase):
    """B6: per-route outcome_text + outcome_text_needs_rewrite.

    Design §8.3 — the route says 'show the player this outcome text' when
    its tier is rolled. Both route AND candidate have outcome_text (B4
    added the candidate's; B6 lifts the route to parity). The
    needs_rewrite flag mirrors the node/option flag — Phase D's copy
    operation sets it True; editing clears it.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.template = MissionTemplateFactory(slug="route-outcome-tmpl")
        cls.entry = MissionNodeFactory(template=cls.template, key="entry", is_entry=True)
        cls.option = MissionOptionFactory(
            node=cls.entry,
            order=0,
            option_kind=OptionKind.BRANCH,
            source_kind=OptionSource.AUTHORED,
        )

    def test_route_outcome_text_defaults_blank(self) -> None:
        route = MissionOptionRouteFactory(option=self.option, outcome_tier=None)
        self.assertEqual(route.outcome_text, "")
        self.assertFalse(route.outcome_text_needs_rewrite)

    def test_route_outcome_text_round_trips(self) -> None:
        route = MissionOptionRouteFactory(
            option=self.option,
            outcome_tier=None,
            outcome_text="You step through into the great hall.",
            outcome_text_needs_rewrite=True,
        )
        route.refresh_from_db()
        self.assertEqual(route.outcome_text, "You step through into the great hall.")
        self.assertTrue(route.outcome_text_needs_rewrite)

    def test_candidate_outcome_text_needs_rewrite_defaults_false(self) -> None:
        # B6 also flags the per-candidate outcome_text (added in B4) for
        # consistency — Phase D's copy operation needs to mark it too.
        route = MissionOptionRouteFactory(option=self.option, outcome_tier=None, is_random_set=True)
        candidate = MissionOptionRouteCandidateFactory(route=route, target_node=self.entry)
        self.assertFalse(candidate.outcome_text_needs_rewrite)

    def test_candidate_outcome_text_needs_rewrite_round_trips(self) -> None:
        route = MissionOptionRouteFactory(option=self.option, outcome_tier=None, is_random_set=True)
        candidate = MissionOptionRouteCandidateFactory(
            route=route,
            target_node=self.entry,
            outcome_text="Inherited copy — rewrite me.",
            outcome_text_needs_rewrite=True,
        )
        candidate.refresh_from_db()
        self.assertTrue(candidate.outcome_text_needs_rewrite)
