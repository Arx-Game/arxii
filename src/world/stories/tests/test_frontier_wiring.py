"""Tests that resolve_episode routes unadvanceable progress through
resolve_frontier (WAITING_FOR_GM / RESTING) instead of leaving it ACTIVE.

resolve_episode raises NoEligibleTransitionError at a terminal/frontier
episode (no outbound transitions). The contract is preserved — the
exception still propagates — but progress.status must now be set to
RESTING / WAITING_FOR_GM as a side effect before the raise.
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from world.stories.constants import (
    BeatOutcome,
    ProgressStatus,
    StoryMaturity,
    StoryScope,
    TransitionMode,
)
from world.stories.exceptions import NoEligibleTransitionError
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    StoryFactory,
    StoryProgressFactory,
    TransitionFactory,
    TransitionRequiredOutcomeFactory,
)
from world.stories.models import StoryProgress
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

    def test_routing_block_is_not_a_frontier(self):
        """BUG 1 regression: outbound transitions exist but none routable.

        The current episode HAS outbound transitions, each gated on a
        routing predicate (TransitionRequiredOutcome) that is not yet
        satisfied, and NO EpisodeProgressionRequirement. get_eligible
        returns [] — but this is a transient routing block, NOT an
        authoring frontier (the next step IS authored, just locked).
        resolve_episode must still raise NoEligibleTransitionError but
        must NOT flip status away from ACTIVE.
        """
        story = StoryFactory(scope=StoryScope.CHARACTER)
        chapter = ChapterFactory(story=story, maturity=StoryMaturity.PLOT)
        ep = EpisodeFactory(chapter=chapter, maturity=StoryMaturity.PLOT)

        # The mission beat is still UNSATISFIED — neither branch routes.
        beat = BeatFactory(episode=ep, outcome=BeatOutcome.UNSATISFIED)

        target_success = EpisodeFactory(chapter=chapter, maturity=StoryMaturity.PLOT)
        target_failure = EpisodeFactory(chapter=chapter, maturity=StoryMaturity.PLOT)

        success_transition = TransitionFactory(
            source_episode=ep,
            target_episode=target_success,
            mode=TransitionMode.AUTO,
            order=0,
        )
        TransitionRequiredOutcomeFactory(
            transition=success_transition,
            beat=beat,
            required_outcome=BeatOutcome.SUCCESS,
        )
        failure_transition = TransitionFactory(
            source_episode=ep,
            target_episode=target_failure,
            mode=TransitionMode.AUTO,
            order=1,
        )
        TransitionRequiredOutcomeFactory(
            transition=failure_transition,
            beat=beat,
            required_outcome=BeatOutcome.FAILURE,
        )

        progress = StoryProgressFactory(story=story, current_episode=ep)

        with self.assertRaises(NoEligibleTransitionError):
            resolve_episode(progress=progress)

        progress.refresh_from_db()
        self.assertEqual(progress.status, ProgressStatus.ACTIVE)

    def test_status_restored_to_active_on_plot_advance(self):
        """BUG 2 regression: a stale frontier status is cleared on advance.

        A clean AUTO transition to a PLOT target. progress.status was
        previously flipped to WAITING_FOR_GM (simulating an earlier
        frontier). After a successful advance through a PLOT episode the
        status must be reconciled back to ACTIVE.
        """
        story = StoryFactory(scope=StoryScope.CHARACTER)
        chapter = ChapterFactory(story=story, maturity=StoryMaturity.PLOT)
        source = EpisodeFactory(chapter=chapter, maturity=StoryMaturity.PLOT)
        target = EpisodeFactory(chapter=chapter, maturity=StoryMaturity.PLOT)
        TransitionFactory(
            source_episode=source,
            target_episode=target,
            mode=TransitionMode.AUTO,
        )
        progress = StoryProgressFactory(story=story, current_episode=source)

        # Simulate a stale frontier status from a prior pause.
        progress.status = ProgressStatus.WAITING_FOR_GM
        progress.save(update_fields=["status"])

        resolve_episode(progress=progress)

        progress.refresh_from_db()
        self.assertEqual(progress.current_episode, target)
        self.assertEqual(progress.status, ProgressStatus.ACTIVE)

    def test_repeated_terminal_resolve_does_not_restamp_last_advanced_at(self):
        """C1 regression: a parked terminal frontier must not reset the
        staleness clock on repeated resolve attempts.

        resolve_episode raises NoEligibleTransitionError at a terminal
        episode and routes through resolve_frontier as a side effect. The
        first call sets the frontier status; subsequent calls must be
        idempotent — last_advanced_at must NOT be re-stamped, otherwise
        days_waiting / stale_stories detection never accrues.
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

        # Force the staleness clock well into the past so the assertion is
        # meaningful even within a single fast test run.
        old = timezone.now() - timedelta(days=30)
        StoryProgress.objects.filter(pk=progress.pk).update(last_advanced_at=old)
        progress.refresh_from_db()
        first = progress.last_advanced_at

        with self.assertRaises(NoEligibleTransitionError):
            resolve_episode(progress=progress)
        progress.refresh_from_db()
        self.assertEqual(progress.status, ProgressStatus.RESTING)
        self.assertEqual(progress.last_advanced_at, first)
