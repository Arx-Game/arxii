"""Non-staff GM authoring permissions over their own StoryScenario graph (#3565).

A GM's scenario is authored through the missions Studio API like staff
content, but scoped: a non-staff caller may only read/write templates (and
their nodes/options/routes/rewards) that are their own StoryScenario, or that
are OPEN + within their GM level's risk ceiling. Everything else 404s
(queryset filtering, never a 403 leak of existence) except template CREATE,
which is 403 outright -- template creation happens only through
POST /api/beats/{id}/scenario/ (see test_views_beat_scenario.py).
"""

from __future__ import annotations

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory, GMTableFactory, seed_default_gm_level_caps
from world.missions.constants import (
    DeedRewardKind,
    DeedRewardSink,
    GiverKind,
    MissionVisibility,
    OptionKind,
    OptionSource,
)
from world.missions.factories import (
    MissionGiverFactory,
    MissionNodeFactory,
    MissionOptionFactory,
    MissionOptionRouteCandidateFactory,
    MissionOptionRouteFactory,
    MissionOptionRouteRewardFactory,
    MissionTemplateFactory,
)
from world.missions.models import MissionNode
from world.missions.services.boards import postings_for_giver
from world.missions.services.opportunities import _nearby_giver_rows
from world.stories.factories import StoryFactory, StoryScenarioFactory
from world.traits.factories import CheckOutcomeFactory


def _gm_with_scenario(username_prefix: str):
    """A JUNIOR GM leading a story, with a template it owns as a StoryScenario."""
    account = AccountFactory(username=f"{username_prefix}-acct", is_staff=False)
    gm_profile = GMProfileFactory(account=account, level=GMLevel.JUNIOR)
    table = GMTableFactory(gm=gm_profile)
    story = StoryFactory(primary_table=table)
    template = MissionTemplateFactory(
        name=f"{username_prefix}-scenario",
        risk_tier=1,
        visibility=MissionVisibility.RESTRICTED,
        base_weight=0,
    )
    StoryScenarioFactory(story=story, template=template)
    entry = MissionNodeFactory(template=template, key="start", is_entry=True)
    check_type = CheckTypeFactory()
    option = MissionOptionFactory(
        node=entry,
        option_kind=OptionKind.CHECK,
        source_kind=OptionSource.AUTHORED,
        authored_check_type=check_type,
    )
    return account, gm_profile, story, template, entry, option


def _gm_with_full_scenario(username_prefix: str):
    """Extends :func:`_gm_with_scenario` with a route + candidate reachable
    from the entry option (#3565 Fix round 1: parent-FK reparenting tests
    need every level -- node, option, route, candidate -- represented).
    """
    account, gm_profile, story, template, entry, option = _gm_with_scenario(username_prefix)
    target = MissionNodeFactory(template=template, key=f"{username_prefix}-target")
    route = MissionOptionRouteFactory(
        option=option,
        outcome_tier=CheckOutcomeFactory(),
        target_node=target,
        is_random_set=True,
    )
    candidate = MissionOptionRouteCandidateFactory(route=route, target_node=target, weight=1)
    return account, gm_profile, story, template, entry, option, target, route, candidate


class ScenarioAuthoringPermissionsTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        seed_default_gm_level_caps()
        (
            cls.owner_account,
            cls.owner_gm,
            cls.owner_story,
            cls.owner_template,
            cls.owner_entry,
            cls.owner_option,
        ) = _gm_with_scenario("owner")
        (
            cls.other_account,
            cls.other_gm,
            cls.other_story,
            cls.other_template,
            cls.other_entry,
            cls.other_option,
        ) = _gm_with_scenario("other")
        cls.staff = AccountFactory(username="staff-scenario-perms", is_staff=True)

    def setUp(self) -> None:
        self.client = APIClient()

    # -- owner can read/write their own scenario --

    def test_owner_can_get_own_template(self) -> None:
        self.client.force_authenticate(self.owner_account)
        resp = self.client.get(f"/api/missions/templates/{self.owner_template.pk}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

    def test_owner_can_patch_own_template(self) -> None:
        self.client.force_authenticate(self.owner_account)
        resp = self.client.patch(
            f"/api/missions/templates/{self.owner_template.pk}/",
            {"summary": "Updated summary."},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data["summary"], "Updated summary.")

    def test_owner_can_get_own_node(self) -> None:
        self.client.force_authenticate(self.owner_account)
        resp = self.client.get(f"/api/missions/nodes/{self.owner_entry.pk}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

    def test_owner_can_get_own_option(self) -> None:
        self.client.force_authenticate(self.owner_account)
        resp = self.client.get(f"/api/missions/options/{self.owner_option.pk}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

    # -- the other GM gets 404 on owner's ids, 403 on template create --

    def test_other_gm_gets_404_on_owners_template(self) -> None:
        self.client.force_authenticate(self.other_account)
        resp = self.client.get(f"/api/missions/templates/{self.owner_template.pk}/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_other_gm_gets_404_on_owners_node(self) -> None:
        self.client.force_authenticate(self.other_account)
        resp = self.client.get(f"/api/missions/nodes/{self.owner_entry.pk}/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_other_gm_gets_404_on_owners_option(self) -> None:
        self.client.force_authenticate(self.other_account)
        resp = self.client.get(f"/api/missions/options/{self.owner_option.pk}/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_other_gm_cannot_post_template(self) -> None:
        self.client.force_authenticate(self.other_account)
        resp = self.client.post(
            "/api/missions/templates/",
            {
                "name": "not-allowed",
                "summary": "x",
                "level_band_min": 1,
                "level_band_max": 10,
                "risk_tier": 1,
                "base_weight": 0,
                "arc_scope": "global",
                "percent_replace": 0,
                "cooldown": "0:00:00",
                "visibility": MissionVisibility.RESTRICTED,
                "availability_rule": {},
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    # -- owner PATCH visibility=open -> 400 --

    def test_owner_cannot_set_visibility_open(self) -> None:
        self.client.force_authenticate(self.owner_account)
        resp = self.client.patch(
            f"/api/missions/templates/{self.owner_template.pk}/",
            {"visibility": MissionVisibility.OPEN},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.data)

    # -- owner POST route reward: sink=item -> 400, sink=money -> 201 --

    def test_owner_route_reward_sink_item_rejected(self) -> None:
        outcome_tier = CheckOutcomeFactory()
        target = MissionNodeFactory(template=self.owner_template, key="target-item")
        route = MissionOptionRouteFactory(
            option=self.owner_option, outcome_tier=outcome_tier, target_node=target
        )
        self.client.force_authenticate(self.owner_account)
        resp = self.client.post(
            "/api/missions/route-rewards/",
            {
                "route": route.pk,
                "kind": DeedRewardKind.IMMEDIATE,
                "sink": DeedRewardSink.ITEM,
                "amount": 1,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.data)

    def test_owner_route_reward_sink_money_accepted(self) -> None:
        outcome_tier = CheckOutcomeFactory()
        target = MissionNodeFactory(template=self.owner_template, key="target-money")
        route = MissionOptionRouteFactory(
            option=self.owner_option, outcome_tier=outcome_tier, target_node=target
        )
        self.client.force_authenticate(self.owner_account)
        resp = self.client.post(
            "/api/missions/route-rewards/",
            {
                "route": route.pk,
                "kind": DeedRewardKind.IMMEDIATE,
                "sink": DeedRewardSink.MONEY,
                "amount": 50,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)

    # -- staff unaffected --

    def test_staff_can_get_and_patch_any_template(self) -> None:
        self.client.force_authenticate(self.staff)
        resp = self.client.get(f"/api/missions/templates/{self.owner_template.pk}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        resp = self.client.patch(
            f"/api/missions/templates/{self.owner_template.pk}/",
            {"visibility": MissionVisibility.OPEN},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)


class ScenarioTemplateFrontDoorExclusionTests(TestCase):
    """A scenario template never surfaces as a quest, even attached to a giver (#3565)."""

    def test_postings_for_giver_excludes_scenario_template(self) -> None:
        story = StoryFactory()
        template = MissionTemplateFactory(
            name="front-door-board", visibility=MissionVisibility.OPEN
        )
        MissionNodeFactory(template=template, key="entry", is_entry=True)
        StoryScenarioFactory(story=story, template=template)
        character = CharacterSheetFactory().character
        board_obj = ObjectDBFactory()
        giver = MissionGiverFactory(giver_kind=GiverKind.BOARD, target=board_obj)
        giver.templates.add(template)
        self.assertEqual(postings_for_giver(giver, character), [])

    def test_nearby_trigger_giver_excludes_scenario_template(self) -> None:
        story = StoryFactory()
        template = MissionTemplateFactory(
            name="front-door-trigger", visibility=MissionVisibility.OPEN
        )
        MissionNodeFactory(template=template, key="entry", is_entry=True)
        StoryScenarioFactory(story=story, template=template)
        character = CharacterSheetFactory().character
        giver = MissionGiverFactory(giver_kind=GiverKind.ROOM_TRIGGER)
        giver.templates.add(template)
        self.assertEqual(_nearby_giver_rows(giver, character, None), [])


class ScenarioChildReparentingTests(TestCase):
    """A non-staff GM cannot re-parent a child row onto a template they do
    not lead by PATCHing its parent FK (#3565 Fix round 1, CRITICAL 1).

    ``IsStaffOrScenarioOwner.has_object_permission`` only ever checked the
    OLD parent (the object as it exists pre-write); ``ScenarioOwnedChildMixin``
    only gated ``perform_create``. So a PATCH re-pointing the parent FK onto
    a template the caller doesn't lead sailed through unchecked at every
    level (node.template, option.node, route.option, candidate.route,
    reward.route/candidate). Each pair below proves: (1) re-parenting onto a
    template the caller does not lead is rejected (403) and the row is
    unchanged, and (2) re-parenting onto a destination still within the
    caller's own scope succeeds.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        seed_default_gm_level_caps()
        (
            cls.owner_account,
            cls.owner_gm,
            cls.owner_story,
            cls.owner_template,
            cls.owner_entry,
            cls.owner_option,
            cls.owner_target,
            cls.owner_route,
            cls.owner_candidate,
        ) = _gm_with_full_scenario("reparent-owner")
        (
            cls.other_account,
            cls.other_gm,
            cls.other_story,
            cls.other_template,
            cls.other_entry,
            cls.other_option,
            cls.other_target,
            cls.other_route,
            cls.other_candidate,
        ) = _gm_with_full_scenario("reparent-other")

        # A second node/option/route within owner_template so "reparent
        # within your own scope" has an in-scope destination to move to at
        # every level below the template itself.
        cls.owner_entry_2 = MissionNodeFactory(template=cls.owner_template, key="second-node")
        check_type = CheckTypeFactory()
        cls.owner_option_2 = MissionOptionFactory(
            node=cls.owner_entry_2,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.AUTHORED,
            authored_check_type=check_type,
        )
        cls.owner_route_2 = MissionOptionRouteFactory(
            option=cls.owner_option_2,
            outcome_tier=CheckOutcomeFactory(),
            target_node=cls.owner_target,
            is_random_set=True,
        )

        # A second template owned by the SAME GM (another StoryScenario on
        # the same story) -- a node's parent IS its template, so there is no
        # in-template destination to move a node to; this is the only level
        # that needs a second owned template rather than a second in-template
        # parent.
        cls.owner_template_2 = MissionTemplateFactory(
            name="reparent-owner-scenario-2",
            risk_tier=1,
            visibility=MissionVisibility.RESTRICTED,
            base_weight=0,
        )
        StoryScenarioFactory(story=cls.owner_story, template=cls.owner_template_2)

        cls.owner_reward = MissionOptionRouteRewardFactory(
            route=cls.owner_route,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.MONEY,
            amount=10,
        )

    def setUp(self) -> None:
        self.client = APIClient()

    # -- node.template --

    def test_node_cannot_reparent_to_unowned_template(self) -> None:
        self.client.force_authenticate(self.owner_account)
        resp = self.client.patch(
            f"/api/missions/nodes/{self.owner_entry_2.pk}/",
            {"template": self.other_template.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN, resp.data)
        self.owner_entry_2.refresh_from_db()
        self.assertEqual(self.owner_entry_2.template_id, self.owner_template.pk)

    def test_node_can_reparent_within_own_scope(self) -> None:
        self.client.force_authenticate(self.owner_account)
        resp = self.client.patch(
            f"/api/missions/nodes/{self.owner_entry_2.pk}/",
            {"template": self.owner_template_2.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.owner_entry_2.refresh_from_db()
        self.assertEqual(self.owner_entry_2.template_id, self.owner_template_2.pk)

    # -- option.node --

    def test_option_cannot_reparent_to_unowned_node(self) -> None:
        self.client.force_authenticate(self.owner_account)
        resp = self.client.patch(
            f"/api/missions/options/{self.owner_option_2.pk}/",
            {"node": self.other_entry.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN, resp.data)
        self.owner_option_2.refresh_from_db()
        self.assertEqual(self.owner_option_2.node_id, self.owner_entry_2.pk)

    def test_option_can_reparent_within_own_scope(self) -> None:
        self.client.force_authenticate(self.owner_account)
        resp = self.client.patch(
            f"/api/missions/options/{self.owner_option_2.pk}/",
            {"node": self.owner_entry.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.owner_option_2.refresh_from_db()
        self.assertEqual(self.owner_option_2.node_id, self.owner_entry.pk)

    # -- route.option --

    def test_route_cannot_reparent_to_unowned_option(self) -> None:
        self.client.force_authenticate(self.owner_account)
        resp = self.client.patch(
            f"/api/missions/routes/{self.owner_route_2.pk}/",
            {"option": self.other_option.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN, resp.data)
        self.owner_route_2.refresh_from_db()
        self.assertEqual(self.owner_route_2.option_id, self.owner_option_2.pk)

    def test_route_can_reparent_within_own_scope(self) -> None:
        self.client.force_authenticate(self.owner_account)
        resp = self.client.patch(
            f"/api/missions/routes/{self.owner_route_2.pk}/",
            {"option": self.owner_option.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.owner_route_2.refresh_from_db()
        self.assertEqual(self.owner_route_2.option_id, self.owner_option.pk)

    # -- candidate.route --

    def test_candidate_cannot_reparent_to_unowned_route(self) -> None:
        self.client.force_authenticate(self.owner_account)
        resp = self.client.patch(
            f"/api/missions/route-candidates/{self.owner_candidate.pk}/",
            {"route": self.other_route.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN, resp.data)
        self.owner_candidate.refresh_from_db()
        self.assertEqual(self.owner_candidate.route_id, self.owner_route.pk)

    def test_candidate_can_reparent_within_own_scope(self) -> None:
        self.client.force_authenticate(self.owner_account)
        resp = self.client.patch(
            f"/api/missions/route-candidates/{self.owner_candidate.pk}/",
            {"route": self.owner_route_2.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.owner_candidate.refresh_from_db()
        self.assertEqual(self.owner_candidate.route_id, self.owner_route_2.pk)

    # -- reward.route --

    def test_reward_cannot_reparent_to_unowned_route(self) -> None:
        self.client.force_authenticate(self.owner_account)
        resp = self.client.patch(
            f"/api/missions/route-rewards/{self.owner_reward.pk}/",
            {"route": self.other_route.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN, resp.data)
        self.owner_reward.refresh_from_db()
        self.assertEqual(self.owner_reward.route_id, self.owner_route.pk)

    def test_reward_can_reparent_within_own_scope(self) -> None:
        self.client.force_authenticate(self.owner_account)
        resp = self.client.patch(
            f"/api/missions/route-rewards/{self.owner_reward.pk}/",
            {"route": self.owner_route_2.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.owner_reward.refresh_from_db()
        self.assertEqual(self.owner_reward.route_id, self.owner_route_2.pk)


class NodeCopyActionPermissionTests(TestCase):
    """POST /api/missions/nodes/{id}/copy/ and .../copy-subtree/ -- object-level
    GM gate (#3565 Fix round 1, IMPORTANT 3).

    These actions were not explicitly force-staffed (unlike
    MissionTemplateViewSet.copy/.assign), so they inherit the viewset's
    IsStaffOrScenarioOwner: a non-owning GM's request never reaches the
    object (queryset-filtered out, 404) or is rejected at the object-level
    unsafe-method check (403) -- either way, nothing is created.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        seed_default_gm_level_caps()
        (
            cls.owner_account,
            cls.owner_gm,
            cls.owner_story,
            cls.owner_template,
            cls.owner_entry,
            cls.owner_option,
        ) = _gm_with_scenario("copy-owner")
        (
            cls.other_account,
            cls.other_gm,
            cls.other_story,
            cls.other_template,
            cls.other_entry,
            cls.other_option,
        ) = _gm_with_scenario("copy-other")

    def setUp(self) -> None:
        self.client = APIClient()

    def test_owner_can_copy_own_node(self) -> None:
        self.client.force_authenticate(self.owner_account)
        resp = self.client.post(
            f"/api/missions/nodes/{self.owner_entry.pk}/copy/",
            {"new_key": "owner-copy"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)

    def test_owner_can_copy_subtree_own_node(self) -> None:
        self.client.force_authenticate(self.owner_account)
        resp = self.client.post(
            f"/api/missions/nodes/{self.owner_entry.pk}/copy-subtree/",
            {"new_key_prefix": "owner-subtree"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)

    def test_other_gm_cannot_copy_owners_node(self) -> None:
        before = MissionNode.objects.filter(template=self.owner_template).count()
        self.client.force_authenticate(self.other_account)
        resp = self.client.post(
            f"/api/missions/nodes/{self.owner_entry.pk}/copy/",
            {"new_key": "other-copy"},
            format="json",
        )
        self.assertIn(
            resp.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND), resp.data
        )
        after = MissionNode.objects.filter(template=self.owner_template).count()
        self.assertEqual(before, after)

    def test_other_gm_cannot_copy_subtree_owners_node(self) -> None:
        before = MissionNode.objects.filter(template=self.owner_template).count()
        self.client.force_authenticate(self.other_account)
        resp = self.client.post(
            f"/api/missions/nodes/{self.owner_entry.pk}/copy-subtree/",
            {"new_key_prefix": "other-subtree"},
            format="json",
        )
        self.assertIn(
            resp.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND), resp.data
        )
        after = MissionNode.objects.filter(template=self.owner_template).count()
        self.assertEqual(before, after)
