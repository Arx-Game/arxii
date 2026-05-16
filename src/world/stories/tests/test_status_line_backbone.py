from django.test import TestCase

from world.stories.constants import ProgressStatus, StoryScope
from world.stories.factories import (
    ChapterFactory,
    EpisodeFactory,
    StoryFactory,
    StoryProgressFactory,
)
from world.stories.services.dashboards import compute_story_status_line


class StatusLineTests(TestCase):
    def _progress(self, status):
        story = StoryFactory(scope=StoryScope.CHARACTER)
        ep = EpisodeFactory(chapter=ChapterFactory(story=story))
        return StoryProgressFactory(story=story, current_episode=ep, status=status)

    def test_waiting_for_gm_copy_is_player_safe(self):
        line = compute_story_status_line(self._progress(ProgressStatus.WAITING_FOR_GM))
        self.assertTrue(line)
        self.assertNotIn("over", line.lower())
        self.assertNotIn("done", line.lower())

    def test_resting_copy_is_ambiguous_not_final(self):
        line = compute_story_status_line(self._progress(ProgressStatus.RESTING))
        self.assertNotIn("complete", line.lower())
        self.assertNotIn("the end", line.lower())
