"""BeatViewSet.assign_mission action — GM-tier mission assignment (#2048)."""

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.factories import GMProfileFactory, GMTableFactory
from world.missions.factories import (
    MissionNodeFactory,
    MissionOptionFactory,
    MissionOptionRouteFactory,
    MissionTemplateFactory,
)
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    StoryFactory,
)


def _make_template_with_branch_terminal():
    template = MissionTemplateFactory()
    entry = MissionNodeFactory(template=template, key="entry", is_entry=True)
    option = MissionOptionFactory(node=entry)
    MissionOptionRouteFactory(option=option, target_node=None, outcome_tier=None)
    return template


class AssignMissionActionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.template = _make_template_with_branch_terminal()
        self.story = StoryFactory()
        self.chapter = ChapterFactory(story=self.story)
        self.episode = EpisodeFactory(chapter=self.chapter)
        self.beat = BeatFactory(episode=self.episode, required_mission=self.template)
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character

    def test_lead_gm_can_assign(self):
        gm_account = AccountFactory(is_staff=False)
        gm_profile = GMProfileFactory(account=gm_account)
        table = GMTableFactory(gm=gm_profile)
        self.story.primary_table = table
        self.story.save()

        self.client.force_authenticate(user=gm_account)
        response = self.client.post(
            f"/api/beats/{self.beat.pk}/assign-mission/",
            {"character": self.character.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        from world.missions.models import MissionInstance

        instance = MissionInstance.objects.get(template=self.template)
        self.assertEqual(instance.source_beat_id, self.beat.pk)

    def test_non_gm_cannot_assign(self):
        account = AccountFactory(is_staff=False)
        self.client.force_authenticate(user=account)
        response = self.client.post(
            f"/api/beats/{self.beat.pk}/assign-mission/",
            {"character": self.character.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 403, response.content)

    def test_staff_can_assign(self):
        staff = AccountFactory(is_staff=True)
        self.client.force_authenticate(user=staff)
        response = self.client.post(
            f"/api/beats/{self.beat.pk}/assign-mission/",
            {"character": self.character.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
