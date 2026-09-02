"""POST /api/beats/{id}/scenario/ -- GM authors a scenario graph as a beat's body (#3565)."""

from __future__ import annotations

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory, GMTableFactory, seed_default_gm_level_caps
from world.missions.constants import MissionVisibility
from world.missions.factories import MissionOptionFactory, MissionTemplateFactory
from world.missions.models import MissionNode
from world.stories.constants import BeatKind
from world.stories.factories import BeatFactory, ChapterFactory, EpisodeFactory, StoryFactory
from world.stories.models import StoryScenario


class BeatScenarioActionTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        seed_default_gm_level_caps()
        cls.gm_account = AccountFactory(username="lead-gm-scenario", is_staff=False)
        cls.gm_profile = GMProfileFactory(account=cls.gm_account, level=GMLevel.JUNIOR)
        cls.table = GMTableFactory(gm=cls.gm_profile)
        cls.story = StoryFactory(primary_table=cls.table)
        cls.chapter = ChapterFactory(story=cls.story)
        cls.episode = EpisodeFactory(chapter=cls.chapter)
        cls.beat = BeatFactory(episode=cls.episode, kind=BeatKind.SITUATION, required_mission=None)
        cls.player = AccountFactory(username="player-scenario", is_staff=False)

    def setUp(self) -> None:
        self.client = APIClient()

    def test_lead_gm_creates_scenario(self) -> None:
        self.client.force_authenticate(self.gm_account)
        resp = self.client.post(
            f"/api/beats/{self.beat.pk}/scenario/",
            {"name": "The Sunken Vault", "summary": "A test scenario.", "risk_tier": 1},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        template_id = resp.data["id"]
        self.assertEqual(resp.data["visibility"], MissionVisibility.RESTRICTED)
        self.assertEqual(resp.data["base_weight"], 0)
        self.beat.refresh_from_db()
        self.assertEqual(self.beat.required_mission_id, template_id)
        self.assertTrue(
            StoryScenario.objects.filter(template_id=template_id, story=self.story).exists()
        )
        entry = MissionNode.objects.get(template_id=template_id)
        self.assertTrue(entry.is_entry)
        self.assertEqual(entry.key, "start")

    def test_second_post_returns_200_same_template(self) -> None:
        self.client.force_authenticate(self.gm_account)
        first = self.client.post(
            f"/api/beats/{self.beat.pk}/scenario/",
            {"name": "Repeat Scenario", "summary": "First.", "risk_tier": 1},
            format="json",
        )
        self.assertEqual(first.status_code, status.HTTP_201_CREATED, first.data)
        second = self.client.post(
            f"/api/beats/{self.beat.pk}/scenario/",
            {"name": "Repeat Scenario Ignored", "summary": "Second.", "risk_tier": 1},
            format="json",
        )
        self.assertEqual(second.status_code, status.HTTP_200_OK, second.data)
        self.assertEqual(second.data["id"], first.data["id"])

    def test_catalog_required_mission_rejected(self) -> None:
        catalog_template = MissionTemplateFactory(name="catalog-mission")
        beat = BeatFactory(
            episode=self.episode, kind=BeatKind.SITUATION, required_mission=catalog_template
        )
        self.client.force_authenticate(self.gm_account)
        resp = self.client.post(
            f"/api/beats/{beat.pk}/scenario/",
            {"name": "Overtake attempt", "summary": "x", "risk_tier": 1},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.data)
        self.assertIn("required_mission", resp.data)

    def test_player_cannot_create_scenario(self) -> None:
        self.client.force_authenticate(self.player)
        resp = self.client.post(
            f"/api/beats/{self.beat.pk}/scenario/",
            {"name": "Nope", "summary": "x", "risk_tier": 1},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_beat_as_lead_gm_shows_option_keys(self) -> None:
        self.client.force_authenticate(self.gm_account)
        create_resp = self.client.post(
            f"/api/beats/{self.beat.pk}/scenario/",
            {"name": "Keyed Scenario", "summary": "x", "risk_tier": 1},
            format="json",
        )
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED, create_resp.data)
        template_id = create_resp.data["id"]
        entry = MissionNode.objects.get(template_id=template_id)
        MissionOptionFactory(node=entry, key="fight")

        resp = self.client.get(f"/api/beats/{self.beat.pk}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(resp.data["scenario"])
        self.assertEqual(resp.data["scenario"]["template_id"], template_id)
        self.assertIn("fight", resp.data["scenario"]["option_keys"])

    def test_get_beat_as_player_scenario_is_null(self) -> None:
        self.client.force_authenticate(self.gm_account)
        create_resp = self.client.post(
            f"/api/beats/{self.beat.pk}/scenario/",
            {"name": "Hidden Scenario", "summary": "x", "risk_tier": 1},
            format="json",
        )
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED, create_resp.data)

        self.client.force_authenticate(self.player)
        resp = self.client.get(f"/api/beats/{self.beat.pk}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsNone(resp.data["scenario"])
