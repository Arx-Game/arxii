"""Lazy stakes-arming: first player action activates stakes (#2048).

A GM-assigned mission with a staked source_beat does NOT arm stakes at
assignment time — only when the player first engages (resolve_beat_option).
Abandoning before engagement leaves no contract.
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.missions.constants import OptionKind, OptionSource
from world.missions.factories import (
    MissionNodeFactory,
    MissionOptionFactory,
    MissionOptionRouteFactory,
    MissionTemplateFactory,
)
from world.missions.services.run import gm_assign_mission


class LazyStakesArmingTests(TestCase):
    def test_first_action_arms_stakes(self):
        from world.societies.constants import RenownRisk
        from world.stories.factories import (
            BeatFactory,
            ChapterFactory,
            EpisodeFactory,
            StoryFactory,
        )
        from world.stories.models import StakeContractActivation

        story = StoryFactory()
        chapter = ChapterFactory(story=story)
        episode = EpisodeFactory(chapter=chapter)
        beat = BeatFactory(episode=episode, risk=RenownRisk.LOW)
        template = MissionTemplateFactory()
        entry = MissionNodeFactory(template=template, key="entry", is_entry=True)
        option = MissionOptionFactory(
            node=entry, option_kind=OptionKind.BRANCH, source_kind=OptionSource.AUTHORED
        )
        MissionOptionRouteFactory(option=option, target_node=None)
        sheet = CharacterSheetFactory()
        character = sheet.character

        instance = gm_assign_mission(template, character, beat=beat)
        # No stakes before engagement
        self.assertFalse(StakeContractActivation.objects.filter(beat=beat).exists())

        # First action
        from world.missions.services.play import resolve_beat_option

        resolve_beat_option(instance, character, option_id=option.pk)
        # Stakes should now be armed
        self.assertTrue(StakeContractActivation.objects.filter(beat=beat).exists())
