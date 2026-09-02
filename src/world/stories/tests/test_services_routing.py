"""Authoring-time routing report: dead ends and ambiguity (#3563)."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from world.stories.constants import BeatOutcome, BeatPredicateType, StakeResolutionColumn
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    EpisodeProgressionRequirementFactory,
    StakeFactory,
    StoryFactory,
    TransitionFactory,
    TransitionRequiredOutcomeFactory,
)
from world.stories.services.routing import (
    beat_title,
    routing_report,
    routing_reports_for_episodes,
)


class _Base(TestCase):
    def setUp(self) -> None:
        self.story = StoryFactory()
        self.chapter = ChapterFactory(story=self.story)
        self.episode = EpisodeFactory(chapter=self.chapter, order=1)
        self.next_a = EpisodeFactory(chapter=self.chapter, order=2)
        self.next_b = EpisodeFactory(chapter=self.chapter, order=3)
        self.beat = BeatFactory(
            episode=self.episode,
            predicate_type=BeatPredicateType.OUTCOME_TIER,
            internal_description="Hostage exchange at the docks\nSecond line is dropped",
        )

    def _edge(self, target, order, **rule):
        transition = TransitionFactory(
            source_episode=self.episode, target_episode=target, order=order
        )
        if rule:
            TransitionRequiredOutcomeFactory(transition=transition, **rule)
        return transition


class DeadEndTests(_Base):
    def test_failure_with_no_accepting_edge_is_a_dead_end(self) -> None:
        self._edge(self.next_a, 1, beat=self.beat, required_outcome=BeatOutcome.SUCCESS)
        report = routing_report(self.episode)
        self.assertEqual(
            report.dead_ends,
            (
                f"beat #{self.beat.pk} (Hostage exchange at the docks) = FAILURE: "
                "no transition accepts it",
            ),
        )
        self.assertEqual(report.ambiguities, ())

    def test_failure_edge_clears_the_dead_end(self) -> None:
        self._edge(self.next_a, 1, beat=self.beat, required_outcome=BeatOutcome.SUCCESS)
        self._edge(self.next_b, 2, beat=self.beat, required_outcome=BeatOutcome.FAILURE)
        self.assertEqual(routing_report(self.episode).dead_ends, ())

    def test_frontier_edge_clears_the_dead_end(self) -> None:
        self._edge(self.next_a, 1, beat=self.beat, required_outcome=BeatOutcome.SUCCESS)
        self._edge(None, 2)
        self.assertEqual(routing_report(self.episode).dead_ends, ())

    def test_expired_is_a_dead_end_only_when_the_beat_has_a_deadline(self) -> None:
        self._edge(self.next_a, 1, beat=self.beat, required_outcome=BeatOutcome.SUCCESS)
        self._edge(self.next_b, 2, beat=self.beat, required_outcome=BeatOutcome.FAILURE)
        self.assertEqual(routing_report(self.episode).dead_ends, ())
        self.beat.deadline = timezone.now() + timedelta(days=1)
        self.beat.save()
        lines = routing_report(self.episode).dead_ends
        self.assertEqual(len(lines), 1)
        self.assertIn("= EXPIRED: no transition accepts it", lines[0])

    def test_stake_loss_with_no_accepting_edge_is_a_dead_end(self) -> None:
        stake = StakeFactory(beat=self.beat, player_summary="The hostage")
        self._edge(
            self.next_a,
            1,
            beat=self.beat,
            stake=stake,
            required_outcome="",
            required_stake_column=StakeResolutionColumn.WIN,
        )
        self._edge(self.next_b, 2, beat=self.beat, required_outcome=BeatOutcome.FAILURE)
        lines = routing_report(self.episode).dead_ends
        self.assertEqual(
            lines,
            (
                f"stake #{stake.pk} on beat #{self.beat.pk} (Hostage exchange at the docks)"
                " = LOSS: no transition accepts it",
            ),
        )

    def test_unreferenced_stake_is_never_a_dead_end(self) -> None:
        StakeFactory(beat=self.beat, player_summary="The hostage")
        self._edge(self.next_a, 1, beat=self.beat, required_outcome=BeatOutcome.SUCCESS)
        self._edge(self.next_b, 2, beat=self.beat, required_outcome=BeatOutcome.FAILURE)
        self.assertEqual(routing_report(self.episode).dead_ends, ())

    def test_progression_requirement_adds_the_beat_to_the_candidates(self) -> None:
        EpisodeProgressionRequirementFactory(
            episode=self.episode, beat=self.beat, required_outcome=BeatOutcome.SUCCESS
        )
        self._edge(self.next_a, 1)
        self.assertEqual(routing_report(self.episode).dead_ends, ())
        TransitionRequiredOutcomeFactory(
            transition=self.episode.outbound_transitions.get(),
            beat=self.beat,
            required_outcome=BeatOutcome.SUCCESS,
        )
        self.assertEqual(len(routing_report(self.episode).dead_ends), 1)

    def test_cross_episode_beat_reference_is_inert(self) -> None:
        foreign_beat = BeatFactory(
            episode=self.next_a, predicate_type=BeatPredicateType.OUTCOME_TIER
        )
        self._edge(self.next_b, 1, beat=foreign_beat, required_outcome=BeatOutcome.SUCCESS)
        self.assertEqual(routing_report(self.episode).dead_ends, ())

    def test_no_transitions_means_no_report(self) -> None:
        EpisodeProgressionRequirementFactory(
            episode=self.episode, beat=self.beat, required_outcome=BeatOutcome.SUCCESS
        )
        report = routing_report(self.episode)
        self.assertEqual(report.problems, ())
        self.assertFalse(report.is_ambiguous)


class AmbiguityTests(_Base):
    def test_two_unconstrained_edges_are_ambiguous(self) -> None:
        a = self._edge(self.next_a, 1)
        b = self._edge(self.next_b, 2)
        report = routing_report(self.episode)
        self.assertEqual(report.ambiguous_pairs, ((a.pk, b.pk),))
        self.assertEqual(
            report.ambiguities,
            (
                f"transitions #{a.pk} and #{b.pk} could both be eligible at once; "
                f"#{a.pk} fires first",
            ),
        )
        self.assertTrue(report.is_ambiguous)

    def test_contradicting_edges_are_not_ambiguous(self) -> None:
        self._edge(self.next_a, 1, beat=self.beat, required_outcome=BeatOutcome.SUCCESS)
        self._edge(self.next_b, 2, beat=self.beat, required_outcome=BeatOutcome.FAILURE)
        self.assertEqual(routing_report(self.episode).ambiguities, ())

    def test_problems_concatenates_dead_ends_then_ambiguities(self) -> None:
        self._edge(self.next_a, 1, beat=self.beat, required_outcome=BeatOutcome.SUCCESS)
        self._edge(self.next_b, 2, beat=self.beat, required_outcome=BeatOutcome.SUCCESS)
        report = routing_report(self.episode)
        self.assertEqual(report.problems, report.dead_ends + report.ambiguities)
        self.assertEqual(len(report.dead_ends), 1)
        self.assertEqual(len(report.ambiguities), 1)


class BatchTests(_Base):
    def test_reports_for_several_episodes_in_bounded_queries(self) -> None:
        stake = StakeFactory(beat=self.beat, player_summary="The hostage")
        self._edge(
            self.next_a,
            1,
            beat=self.beat,
            stake=stake,
            required_outcome="",
            required_stake_column=StakeResolutionColumn.WIN,
        )
        other_beat = BeatFactory(episode=self.next_a, predicate_type=BeatPredicateType.OUTCOME_TIER)
        to_b = TransitionFactory(source_episode=self.next_a, target_episode=self.next_b, order=1)
        TransitionRequiredOutcomeFactory(
            transition=to_b, beat=other_beat, required_outcome=BeatOutcome.SUCCESS
        )
        episode_ids = [self.episode.pk, self.next_a.pk, self.next_b.pk]
        with self.assertNumQueries(4):
            reports = routing_reports_for_episodes(episode_ids)
        self.assertEqual(set(reports), {self.episode.pk, self.next_a.pk, self.next_b.pk})
        self.assertEqual(len(reports[self.episode.pk].dead_ends), 2)
        self.assertEqual(len(reports[self.next_a.pk].dead_ends), 1)
        self.assertEqual(reports[self.next_b.pk].problems, ())

    def test_empty_input_returns_empty_map(self) -> None:
        with self.assertNumQueries(0):
            self.assertEqual(routing_reports_for_episodes([]), {})


class BeatTitleTests(TestCase):
    def test_first_line_capped_at_sixty_chars(self) -> None:
        beat = BeatFactory(internal_description=("x" * 80) + "\nsecond")
        self.assertEqual(beat_title(beat), "x" * 60)

    def test_blank_description_is_blank(self) -> None:
        beat = BeatFactory(internal_description="  ")
        self.assertEqual(beat_title(beat), "")
