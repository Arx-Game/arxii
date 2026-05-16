"""Tests that resolve_episode routes unadvanceable progress through
resolve_frontier (WAITING_FOR_GM / RESTING) instead of leaving it ACTIVE.

resolve_episode raises NoEligibleTransitionError at a terminal/frontier
episode (no outbound transitions). The contract is preserved — the
exception still propagates — but progress.status must now be set to
RESTING / WAITING_FOR_GM as a side effect before the raise.
"""

from django.test import TestCase

from world.stories.constants import ProgressStatus, StoryMaturity, StoryScope
from world.stories.exceptions import NoEligibleTransitionError
from world.stories.factories import (
    ChapterFactory,
    EpisodeFactory,
    StoryFactory,
    StoryProgressFactory,
)
from world.stories.services.episodes import resolve_episode


class FrontierWiringTests(TestCase):
    def test_resolving_terminal_plot_episode_rests(self):
        """A terminal PLOT episode with nothing authored ahead → RESTING.

        The whole story is PLOT, so resolve_frontier picks RESTING.
        resolve_episode still raises NoEligibleTransitionError (no
        outbound transitions) — that contract is unchanged — but the
        status side effect must have landed before the raise.
        """
        story = StoryFactory(scope=StoryScope.CHARACTER)
        chapter = ChapterFactory(story=story, maturity=StoryMaturity.PLOT)
        ep = EpisodeFactory(
            chapter=chapter,
            maturity=StoryMaturity.PLOT,
            resting_conclusion="It ends here.",
            is_ending=True,
        )
        progress = StoryProgressFactory(story=story, current_episode=ep)

        with self.assertRaises(NoEligibleTransitionError):
            resolve_episode(progress=progress)

        progress.refresh_from_db()
        self.assertEqual(progress.status, ProgressStatus.RESTING)

    def test_resolving_terminal_episode_with_immature_content_waits_for_gm(self):
        """If any episode in the story is below PLOT, the frontier lands in
        WAITING_FOR_GM (the author intends more content)."""
        story = StoryFactory(scope=StoryScope.CHARACTER)
        chapter = ChapterFactory(story=story, maturity=StoryMaturity.PLOT)
        ep = EpisodeFactory(
            chapter=chapter,
            maturity=StoryMaturity.PLOT,
            resting_conclusion="Paused here.",
            is_ending=True,
        )
        # A sibling episode still being authored (below PLOT).
        EpisodeFactory(chapter=chapter, maturity=StoryMaturity.OUTLINE)
        progress = StoryProgressFactory(story=story, current_episode=ep)

        with self.assertRaises(NoEligibleTransitionError):
            resolve_episode(progress=progress)

        progress.refresh_from_db()
        self.assertEqual(progress.status, ProgressStatus.WAITING_FOR_GM)
