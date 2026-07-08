"""GM-tier mission assignment via gm_assign_mission (#2048).

Direct drop (no accept gate) — the player consents by pursuing.
Stakes arm on first engagement, not at drop time.
"""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.missions.factories import (
    MissionNodeFactory,
    MissionTemplateFactory,
)


def _make_template_with_entry():
    template = MissionTemplateFactory()
    MissionNodeFactory(template=template, key="entry", is_entry=True)
    return template


class GMAssignMissionTests(TestCase):
    def test_gm_assign_creates_instance_with_source_beat(self):
        from world.stories.factories import (
            BeatFactory,
            ChapterFactory,
            EpisodeFactory,
            StoryFactory,
        )

        story = StoryFactory()
        chapter = ChapterFactory(story=story)
        episode = EpisodeFactory(chapter=chapter)
        beat = BeatFactory(episode=episode)
        template = _make_template_with_entry()
        character = CharacterFactory(db_key="GMAssignChar")

        from world.missions.services.run import gm_assign_mission

        instance = gm_assign_mission(template, character, beat=beat)
        self.assertEqual(instance.source_beat_id, beat.pk)
        self.assertEqual(instance.template_id, template.pk)
        holder = instance.participants.get(is_contract_holder=True)
        self.assertEqual(holder.character_id, character.pk)

    def test_gm_assign_without_beat(self):
        template = _make_template_with_entry()
        character = CharacterFactory(db_key="NoBeatChar")

        from world.missions.services.run import gm_assign_mission

        instance = gm_assign_mission(template, character)
        self.assertIsNone(instance.source_beat_id)

    def test_gm_assign_does_not_activate_stakes(self):
        """Stakes arm on first engagement, not at assignment time."""
        from world.societies.constants import RenownRisk
        from world.stories.factories import (
            BeatFactory,
            ChapterFactory,
            EpisodeFactory,
            StoryFactory,
        )

        story = StoryFactory()
        chapter = ChapterFactory(story=story)
        episode = EpisodeFactory(chapter=chapter)
        beat = BeatFactory(episode=episode, risk=RenownRisk.LOW)
        template = _make_template_with_entry()
        character = CharacterFactory(db_key="NoStakesChar")

        from world.missions.services.run import gm_assign_mission

        gm_assign_mission(template, character, beat=beat)
        from world.stories.models import StakeContractActivation

        self.assertFalse(StakeContractActivation.objects.filter(beat=beat).exists())
