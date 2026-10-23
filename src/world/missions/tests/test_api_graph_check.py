"""The Mission Studio graph check endpoint (#4558)."""

from unittest.mock import patch

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.combat.constants import EncounterOutcome, RiskLevel
from world.combat.models import EncounterOutcomeMapping
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory, GMTableFactory
from world.missions.constants import (
    ConflictMode,
    ExternalAct,
    GraphProblemKind,
    JointCombine,
    OptionKind,
)
from world.missions.factories import (
    MissionNodeFactory,
    MissionOptionFactory,
    MissionOptionRouteCandidateFactory,
    MissionOptionRouteFactory,
    MissionTemplateFactory,
)
from world.missions.services import graph_check
from world.stories.factories import StoryFactory, StoryScenarioFactory
from world.traits.factories import (
    CheckOutcomeFactory,
    ResultChartFactory,
    ResultChartOutcomeFactory,
)

TIERS = [
    ("Critical Failure", -2),
    ("Failure", -1),
    ("Partial Success", 0),
    ("Success", 1),
    ("Critical Success", 2),
]


def _url(template) -> str:
    return f"/api/missions/templates/{template.pk}/graph-check/"


class GraphCheckTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(username="staff-graph-check", is_staff=True)
        cls.check_type = CheckTypeFactory()
        cls.tiers = {name: CheckOutcomeFactory(name=name, success_level=lvl) for name, lvl in TIERS}
        chart = ResultChartFactory()
        for roll, tier in enumerate(cls.tiers.values(), start=1):
            ResultChartOutcomeFactory(chart=chart, outcome=tier, min_roll=roll, max_roll=roll)

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(self.staff)

    def _problems(self, template) -> list[dict]:
        response = self.client.get(_url(template))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response.data["problems"]

    def _kinds(self, template) -> list[str]:
        return [p["kind"] for p in self._problems(template)]

    def _template(self, name: str):
        template = MissionTemplateFactory(name=name)
        entry = MissionNodeFactory(template=template, key="entry", is_entry=True)
        return template, entry

    def _check_option(self, node, tiers, **kwargs):
        option = MissionOptionFactory(
            node=node, option_kind=OptionKind.CHECK, authored_check_type=self.check_type, **kwargs
        )
        routes = [
            MissionOptionRouteFactory(option=option, outcome_tier=self.tiers[name])
            for name in tiers
        ]
        return option, routes

    def test_template_with_no_nodes_reports_only_no_entry(self) -> None:
        template = MissionTemplateFactory(name="empty-graph")
        problems = self._problems(template)
        self.assertEqual([p["kind"] for p in problems], [GraphProblemKind.NO_ENTRY])
        self.assertIsNone(problems[0]["node"])
        self.assertEqual(problems[0]["missing_tiers"], [])

    def test_no_entry_skips_unreachable(self) -> None:
        template = MissionTemplateFactory(name="no-entry-graph")
        MissionNodeFactory(template=template, key="a")
        self.assertEqual(self._kinds(template), [GraphProblemKind.NO_ENTRY])

    def test_unreachable_node_flagged(self) -> None:
        template, _ = self._template("unreachable-graph")
        orphan = MissionNodeFactory(template=template, key="orphan")
        problems = self._problems(template)
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0]["kind"], GraphProblemKind.UNREACHABLE_NODE)
        self.assertEqual(problems[0]["node"], orphan.pk)
        self.assertEqual(problems[0]["message"], 'Nothing leads to "orphan" from the entry node.')

    def test_nodes_reached_by_candidate_branch_target_and_tracks_are_not_flagged(self) -> None:
        template, entry = self._template("reach-graph")
        via_candidate = MissionNodeFactory(template=template, key="via-candidate")
        via_branch = MissionNodeFactory(template=template, key="via-branch")
        via_success = MissionNodeFactory(template=template, key="via-success")
        via_failure = MissionNodeFactory(template=template, key="via-failure")
        entry.track_successes = 1
        entry.track_failures = 1
        entry.track_success_target = via_success
        entry.track_failure_target = via_failure
        entry.save()
        MissionOptionFactory(node=entry, branch_target=via_branch)
        random_option = MissionOptionFactory(node=entry)
        route = MissionOptionRouteFactory(option=random_option, is_random_set=True)
        MissionOptionRouteCandidateFactory(route=route, target_node=via_candidate)
        self.assertEqual(self._problems(template), [])

    def test_reachable_chain_through_route_target(self) -> None:
        template, entry = self._template("chain-graph")
        second = MissionNodeFactory(template=template, key="second")
        third = MissionNodeFactory(template=template, key="third")
        MissionOptionRouteFactory(option=MissionOptionFactory(node=entry), target_node=second)
        MissionOptionRouteFactory(option=MissionOptionFactory(node=second), target_node=third)
        self.assertEqual(self._problems(template), [])

    def test_branch_and_external_act_without_routes_are_endings(self) -> None:
        template, entry = self._template("endings-graph")
        MissionOptionFactory(node=entry, option_kind=OptionKind.BRANCH)
        MissionOptionFactory(
            node=entry,
            option_kind=OptionKind.EXTERNAL_ACT,
            required_act=ExternalAct.TECHNIQUE_CAST,
        )
        self.assertEqual(self._problems(template), [])

    def test_check_missing_tiers_listed_worst_first(self) -> None:
        template, entry = self._template("missing-tiers-graph")
        option, _ = self._check_option(
            entry, ["Success", "Partial Success", "Failure"], key="pick-lock"
        )
        problems = self._problems(template)
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0]["kind"], GraphProblemKind.MISSING_TIERS)
        self.assertEqual(problems[0]["missing_tiers"], ["Critical Failure", "Critical Success"])
        self.assertEqual(problems[0]["option"], option.pk)
        self.assertEqual(
            problems[0]["message"],
            '"pick-lock" has no route for: Critical Failure, Critical Success.',
        )

    def test_check_with_every_tier_is_clean(self) -> None:
        template, entry = self._template("all-tiers-graph")
        self._check_option(entry, [name for name, _ in TIERS])
        self.assertEqual(self._problems(template), [])

    def test_contest_option_is_checked_like_a_check(self) -> None:
        template, entry = self._template("contest-graph")
        MissionOptionFactory(
            node=entry,
            option_kind=OptionKind.CONTEST,
            key="duel",
            authored_check_type=self.check_type,
            opposition_check_type=self.check_type,
            opposition_sheet=CharacterSheetFactory(),
        )
        self.assertEqual(self._kinds(template), [GraphProblemKind.MISSING_TIERS])

    def test_option_label_falls_back_to_framing_then_order(self) -> None:
        template, entry = self._template("label-graph")
        MissionOptionFactory(
            node=entry,
            option_kind=OptionKind.CHECK,
            authored_check_type=self.check_type,
            key="",
            authored_ic_framing="x" * 60,
        )
        second = MissionNodeFactory(template=template, key="second")
        MissionOptionFactory(node=entry, key="go-second", branch_target=second)
        MissionOptionFactory(
            node=second,
            option_kind=OptionKind.CHECK,
            authored_check_type=self.check_type,
            key="",
            order=7,
        )
        messages = [p["message"] for p in self._problems(template)]
        self.assertTrue(messages[0].startswith('"' + "x" * 40 + '" has no route'))
        self.assertTrue(messages[1].startswith('"option 7" has no route'))

    def _joint_entry(self, name: str):
        template = MissionTemplateFactory(name=name)
        entry = MissionNodeFactory(
            template=template,
            key="entry",
            is_entry=True,
            conflict_mode=ConflictMode.JOINT,
            joint_combine=JointCombine.ANY,
        )
        return template, entry

    def test_joint_check_missing_tiers_are_reported_like_any_node(self) -> None:
        template, entry = self._joint_entry("joint-tiers-graph")
        option, _ = self._check_option(entry, ["Success", "Failure"])
        problems = self._problems(template)
        self.assertEqual([p["kind"] for p in problems], [GraphProblemKind.MISSING_TIERS])
        self.assertEqual(problems[0]["option"], option.pk)
        self.assertEqual(
            problems[0]["missing_tiers"],
            ["Critical Failure", "Partial Success", "Critical Success"],
        )

    def test_joint_check_with_every_tier_is_clean(self) -> None:
        template, entry = self._joint_entry("joint-ok-graph")
        self._check_option(entry, [name for name, _ in TIERS])
        self.assertEqual(self._problems(template), [])

    def test_joint_check_missing_a_bucket_flagged_when_no_chart_names_a_tier(self) -> None:
        template, entry = self._joint_entry("joint-bad-graph")
        option, _ = self._check_option(entry, ["Success", "Critical Success"])
        with patch.object(graph_check, "_rollable_check_tiers", return_value=set()):
            problems = self._problems(template)
        self.assertEqual([p["kind"] for p in problems], [GraphProblemKind.JOINT_MISSING_BUCKET])
        self.assertEqual(problems[0]["option"], option.pk)

    def test_branch_option_on_joint_node_flagged(self) -> None:
        template, entry = self._joint_entry("joint-branch-graph")
        option = MissionOptionFactory(node=entry, option_kind=OptionKind.BRANCH, key="split")
        problems = self._problems(template)
        self.assertEqual([p["kind"] for p in problems], [GraphProblemKind.JOINT_MISSING_BUCKET])
        self.assertEqual(problems[0]["option"], option.pk)
        self.assertEqual(
            problems[0]["message"],
            '"split" is a branch on a joint node, which can\'t decide where the group goes.',
        )

    def test_branch_target_makes_the_options_tier_less_route_unreachable(self) -> None:
        template, entry = self._template("branch-target-graph")
        via_target = MissionNodeFactory(template=template, key="via-target")
        via_route = MissionNodeFactory(template=template, key="via-route")
        option = MissionOptionFactory(
            node=entry, option_kind=OptionKind.BRANCH, branch_target=via_target
        )
        MissionOptionRouteFactory(option=option, target_node=via_route)
        problems = self._problems(template)
        self.assertEqual([p["node"] for p in problems], [via_route.pk])
        self.assertEqual(problems[0]["kind"], GraphProblemKind.UNREACHABLE_NODE)

    def test_branch_tiered_route_is_never_followed(self) -> None:
        template, entry = self._template("branch-tiered-graph")
        via_tiered = MissionNodeFactory(template=template, key="via-tiered")
        option = MissionOptionFactory(node=entry, option_kind=OptionKind.BRANCH)
        MissionOptionRouteFactory(
            option=option, outcome_tier=self.tiers["Success"], target_node=via_tiered
        )
        self.assertEqual([p["node"] for p in self._problems(template)], [via_tiered.pk])

    def test_encounter_without_risk_level_flagged(self) -> None:
        template, entry = self._template("no-risk-graph")
        option = MissionOptionFactory(
            node=entry,
            option_kind=OptionKind.ENCOUNTER,
            encounter_risk_level=RiskLevel.LOW,
            key="fight",
        )
        # The model refuses a blank risk level on save; legacy rows can still hold one.
        option.encounter_risk_level = ""
        type(option).objects.bulk_update_with_reason(
            [option], ["encounter_risk_level"], reason="legacy row with a blank risk level"
        )
        self.assertEqual(self._kinds(template), [GraphProblemKind.NO_RISK_LEVEL])

    def test_encounter_missing_mapped_tiers_flagged(self) -> None:
        for outcome, tier in (
            (EncounterOutcome.VICTORY, "Success"),
            (EncounterOutcome.DEFEAT, "Failure"),
        ):
            EncounterOutcomeMapping.objects.create(
                outcome=outcome, risk_level=RiskLevel.HIGH, check_outcome=self.tiers[tier]
            )
        template, entry = self._template("encounter-tiers-graph")
        option = MissionOptionFactory(
            node=entry,
            option_kind=OptionKind.ENCOUNTER,
            encounter_risk_level=RiskLevel.HIGH,
            key="fight",
        )
        MissionOptionRouteFactory(option=option, outcome_tier=self.tiers["Success"])
        problems = self._problems(template)
        self.assertEqual([p["kind"] for p in problems], [GraphProblemKind.MISSING_TIERS])
        self.assertEqual(problems[0]["missing_tiers"], ["Failure"])

    def test_empty_random_set_flagged(self) -> None:
        template, entry = self._template("empty-random-graph")
        option = MissionOptionFactory(node=entry, key="roll-dice")
        route = MissionOptionRouteFactory(option=option, is_random_set=True)
        problems = self._problems(template)
        self.assertEqual([p["kind"] for p in problems], [GraphProblemKind.EMPTY_RANDOM_SET])
        self.assertEqual(problems[0]["route"], route.pk)
        self.assertEqual(
            problems[0]["message"],
            'A random route on "roll-dice" has no candidates, so the mission ends there.',
        )

    def test_problems_ordered_by_node_option_route(self) -> None:
        template, entry = self._template("order-graph")
        first = MissionOptionFactory(
            node=entry,
            option_kind=OptionKind.CHECK,
            authored_check_type=self.check_type,
            key="first",
        )
        second = MissionOptionFactory(
            node=entry,
            option_kind=OptionKind.CHECK,
            authored_check_type=self.check_type,
            key="second",
        )
        orphan = MissionNodeFactory(template=template, key="orphan")
        problems = self._problems(template)
        self.assertEqual(
            [(p["node"], p["option"]) for p in problems],
            [(entry.pk, first.pk), (entry.pk, second.pk), (orphan.pk, None)],
        )

    def test_query_count_does_not_grow_with_the_graph(self) -> None:
        small, small_entry = self._template("small-graph")
        self._check_option(small_entry, ["Success"])
        large, large_entry = self._template("large-graph")
        for index in range(4):
            node = MissionNodeFactory(template=large, key=f"n{index}")
            option, _ = self._check_option(large_entry, ["Success", "Failure"])
            route = MissionOptionRouteFactory(option=option, is_random_set=True)
            MissionOptionRouteCandidateFactory(route=route, target_node=node)
            self._check_option(node, ["Failure"])
        for template in (small, large):
            self.client.get(_url(template))  # warm the per-process caches
        counts = []
        for template in (small, large):
            with CaptureQueriesContext(connection) as queries:
                self.client.get(_url(template))
            counts.append(len(queries))
        self.assertEqual(counts[0], counts[1])


class GraphCheckScopingTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory(username="graph-gm", is_staff=False)
        gm = GMProfileFactory(account=cls.account, level=GMLevel.JUNIOR)
        story = StoryFactory(primary_table=GMTableFactory(gm=gm))
        cls.own = MissionTemplateFactory(name="gm-own-graph", risk_tier=1, visibility="restricted")
        StoryScenarioFactory(story=story, template=cls.own)
        cls.other = MissionTemplateFactory(
            name="gm-other-graph", risk_tier=1, visibility="restricted"
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(self.account)

    def test_lead_gm_reads_own_scenario(self) -> None:
        self.assertEqual(self.client.get(_url(self.own)).status_code, status.HTTP_200_OK)

    def test_other_template_is_404(self) -> None:
        self.assertEqual(self.client.get(_url(self.other)).status_code, status.HTTP_404_NOT_FOUND)

    def test_anonymous_refused(self) -> None:
        response = APIClient().get(_url(self.own))
        self.assertIn(
            response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
        )
