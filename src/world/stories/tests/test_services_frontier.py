from django.test import TestCase

from world.stories.constants import ProgressStatus, StoryMaturity, StoryScope
from world.stories.factories import (
    ChapterFactory,
    EpisodeFactory,
    StoryFactory,
    StoryProgressFactory,
)
from world.stories.services.frontier import resolve_frontier, set_progress_status


class FrontierTests(TestCase):
    def _story_with_episode(self, ep_maturity):
        story = StoryFactory(scope=StoryScope.CHARACTER)
        chapter = ChapterFactory(story=story)
        ep = EpisodeFactory(chapter=chapter, maturity=ep_maturity)
        progress = StoryProgressFactory(story=story, current_episode=ep)
        return story, ep, progress

    def test_resting_when_nothing_immature_remains(self):
        _story, _ep, progress = self._story_with_episode(StoryMaturity.PLOT)
        resolve_frontier(progress)
        progress.refresh_from_db()
        self.assertEqual(progress.status, ProgressStatus.RESTING)

    def test_waiting_for_gm_when_immature_content_remains(self):
        story, _ep, progress = self._story_with_episode(StoryMaturity.PLOT)
        immature_chapter = ChapterFactory(story=story)
        EpisodeFactory(chapter=immature_chapter, maturity=StoryMaturity.PITCH)
        resolve_frontier(progress)
        progress.refresh_from_db()
        self.assertEqual(progress.status, ProgressStatus.WAITING_FOR_GM)

    def test_set_progress_status_helper(self):
        _, _, progress = self._story_with_episode(StoryMaturity.PLOT)
        set_progress_status(progress, ProgressStatus.COMPLETED)
        progress.refresh_from_db()
        self.assertEqual(progress.status, ProgressStatus.COMPLETED)
        self.assertFalse(progress.is_active)
