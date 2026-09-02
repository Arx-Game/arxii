"""Option-key routing, lowest-order tie-break, ambiguity report (#3565)."""

from django.test import TestCase

from world.stories.constants import BeatOutcome, BeatPredicateType
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    StoryFactory,
    StoryProgressFactory,
    TransitionFactory,
    TransitionRequiredOutcomeFactory,
)
from world.stories.services.episodes import resolve_episode
from world.stories.services.routing import routing_report
from world.stories.services.transitions import get_eligible_transitions


class _Base(TestCase):
    def setUp(self) -> None:
        self.story = StoryFactory()
        self.chapter = ChapterFactory(story=self.story)
        self.episode = EpisodeFactory(chapter=self.chapter, order=1)
        self.next_a = EpisodeFactory(chapter=self.chapter, order=2)
        self.next_b = EpisodeFactory(chapter=self.chapter, order=3)
        self.progress = StoryProgressFactory(story=self.story, current_episode=self.episode)
        self.beat = BeatFactory(
            episode=self.episode,
            predicate_type=BeatPredicateType.OUTCOME_TIER,
            outcome=BeatOutcome.SUCCESS,
            outcome_key="negotiate",
        )


class KeyRoutingTests(_Base):
    def test_key_match_required_when_set(self) -> None:
        to_a = TransitionFactory(source_episode=self.episode, target_episode=self.next_a, order=1)
        TransitionRequiredOutcomeFactory(
            transition=to_a,
            beat=self.beat,
            required_outcome=BeatOutcome.SUCCESS,
            required_outcome_key="negotiate",
        )
        to_b = TransitionFactory(source_episode=self.episode, target_episode=self.next_b, order=2)
        TransitionRequiredOutcomeFactory(
            transition=to_b,
            beat=self.beat,
            required_outcome=BeatOutcome.SUCCESS,
            required_outcome_key="fight",
        )
        self.assertEqual(get_eligible_transitions(self.progress), [to_a])

    def test_blank_key_matches_any(self) -> None:
        to_a = TransitionFactory(source_episode=self.episode, target_episode=self.next_a, order=1)
        TransitionRequiredOutcomeFactory(
            transition=to_a,
            beat=self.beat,
            required_outcome=BeatOutcome.SUCCESS,
        )
        self.assertEqual(get_eligible_transitions(self.progress), [to_a])


class TieBreakTests(_Base):
    def test_lowest_order_fires_when_several_eligible(self) -> None:
        later = TransitionFactory(source_episode=self.episode, target_episode=self.next_b, order=5)
        first = TransitionFactory(source_episode=self.episode, target_episode=self.next_a, order=1)
        resolution = resolve_episode(progress=self.progress)
        self.assertEqual(resolution.chosen_transition_id, first.pk)
        self.progress.refresh_from_db()
        self.assertEqual(self.progress.current_episode_id, self.next_a.pk)
        self.assertNotEqual(resolution.chosen_transition_id, later.pk)


class AmbiguityReportTests(_Base):
    def test_two_unconstrained_edges_are_ambiguous(self) -> None:
        a = TransitionFactory(source_episode=self.episode, target_episode=self.next_a, order=1)
        b = TransitionFactory(source_episode=self.episode, target_episode=self.next_b, order=2)
        report = routing_report(self.episode)
        self.assertEqual(report.ambiguous_pairs, ((a.pk, b.pk),))

    def test_contradicting_requirements_are_not_ambiguous(self) -> None:
        a = TransitionFactory(source_episode=self.episode, target_episode=self.next_a, order=1)
        TransitionRequiredOutcomeFactory(
            transition=a, beat=self.beat, required_outcome=BeatOutcome.SUCCESS
        )
        b = TransitionFactory(source_episode=self.episode, target_episode=self.next_b, order=2)
        TransitionRequiredOutcomeFactory(
            transition=b, beat=self.beat, required_outcome=BeatOutcome.FAILURE
        )
        self.assertEqual(routing_report(self.episode).ambiguous_pairs, ())

    def test_same_beat_different_keys_are_not_ambiguous(self) -> None:
        a = TransitionFactory(source_episode=self.episode, target_episode=self.next_a, order=1)
        TransitionRequiredOutcomeFactory(
            transition=a,
            beat=self.beat,
            required_outcome=BeatOutcome.SUCCESS,
            required_outcome_key="negotiate",
        )
        b = TransitionFactory(source_episode=self.episode, target_episode=self.next_b, order=2)
        TransitionRequiredOutcomeFactory(
            transition=b,
            beat=self.beat,
            required_outcome=BeatOutcome.SUCCESS,
            required_outcome_key="fight",
        )
        self.assertEqual(routing_report(self.episode).ambiguous_pairs, ())
