from django.test import TestCase

from world.stories.constants import ProgressStatus, StoryScope
from world.stories.factories import (
    ChapterFactory,
    EpisodeFactory,
    StoryFactory,
    StoryProgressFactory,
)
from world.stories.services.dashboards import compute_story_status_line

# Words that would (wrongly) imply a story is finished. Player-facing copy at a
# pause/rest must never contain any of these; only COMPLETED is legitimately final.
FORBIDDEN_FINALITY_WORDS = ("over", "done", "complete", "the end")


class StatusLineTests(TestCase):
    def _progress(self, status, current_episode=...):
        story = StoryFactory(scope=StoryScope.CHARACTER)
        if current_episode is ...:
            current_episode = EpisodeFactory(chapter=ChapterFactory(story=story))
        return StoryProgressFactory(story=story, current_episode=current_episode, status=status)

    def _assert_no_finality(self, line):
        for word in FORBIDDEN_FINALITY_WORDS:
            self.assertNotIn(word, line.lower())

    def test_waiting_for_gm_copy_is_player_safe(self):
        line = compute_story_status_line(self._progress(ProgressStatus.WAITING_FOR_GM))
        self.assertTrue(line)
        self._assert_no_finality(line)

    def test_resting_copy_is_ambiguous_not_final(self):
        line = compute_story_status_line(self._progress(ProgressStatus.RESTING))
        self.assertTrue(line)
        self._assert_no_finality(line)

    def test_completed_copy_is_final(self):
        line = compute_story_status_line(self._progress(ProgressStatus.COMPLETED))
        self.assertTrue(line)
        self.assertEqual(line, "This story has reached its conclusion.")

    def test_active_with_current_episode_describes_position(self):
        story = StoryFactory(scope=StoryScope.CHARACTER)
        ep = EpisodeFactory(chapter=ChapterFactory(story=story), title="The Sunken Vault")
        progress = StoryProgressFactory(
            story=story, current_episode=ep, status=ProgressStatus.ACTIVE
        )
        line = compute_story_status_line(progress)
        self.assertTrue(line)
        self.assertIn("Sunken Vault", line)
        self._assert_no_finality(line)

    def test_active_without_current_episode_is_prepared_copy(self):
        progress = self._progress(ProgressStatus.ACTIVE, current_episode=None)
        line = compute_story_status_line(progress)
        self.assertTrue(line)
        self.assertIn("being prepared", line.lower())
        self._assert_no_finality(line)
