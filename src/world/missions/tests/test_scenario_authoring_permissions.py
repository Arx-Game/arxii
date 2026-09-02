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
    MissionOptionRouteFactory,
    MissionTemplateFactory,
)
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
