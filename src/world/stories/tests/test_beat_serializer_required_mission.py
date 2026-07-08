"""BeatSerializer.required_mission writable (#2048)."""

from django.test import TestCase
from rest_framework.test import APIRequestFactory

from evennia_extensions.factories import AccountFactory
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
from world.stories.serializers import BeatSerializer


def _make_template_with_branch_terminal():
    template = MissionTemplateFactory()
    entry = MissionNodeFactory(template=template, key="entry", is_entry=True)
    option = MissionOptionFactory(node=entry)
    MissionOptionRouteFactory(option=option, target_node=None, outcome_tier=None)
    return template


class BeatSerializerRequiredMissionTests(TestCase):
    def test_required_mission_is_in_fields(self):
        self.assertIn("required_mission", BeatSerializer.Meta.fields)

    def test_can_set_required_mission(self):
        template = _make_template_with_branch_terminal()
        story = StoryFactory()
        chapter = ChapterFactory(story=story)
        episode = EpisodeFactory(chapter=chapter)
        beat = BeatFactory(episode=episode)
        staff = AccountFactory(is_staff=True)
        factory = APIRequestFactory()
        request = factory.patch("/", {"required_mission": template.pk}, format="json")
        request.user = staff
        serializer = BeatSerializer(
            beat,
            data={"required_mission": template.pk},
            partial=True,
            context={"request": request},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()
        beat.refresh_from_db()
        self.assertEqual(beat.required_mission_id, template.pk)
