"""Tests for world.stories.services.transitions."""

from evennia.utils.test_resources import EvenniaTestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.stories.constants import BeatOutcome, TransitionMode
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    EpisodeProgressionRequirementFactory,
    StoryFactory,
    StoryProgressFactory,
    TransitionFactory,
    TransitionRequiredOutcomeFactory,
)
from world.stories.services.transitions import get_eligible_transitions


class GetEligibleTransitionsTests(EvenniaTestCase):
    """Tests for get_eligible_transitions."""

    def _make_progress(self, episode=None):
        """Build a StoryProgress pointing at the given episode."""
        sheet = CharacterSheetFactory()
        return StoryProgressFactory(character_sheet=sheet, current_episode=episode)

    # ------------------------------------------------------------------
    # Frontier / None guard
    # ------------------------------------------------------------------

    def test_current_episode_none_returns_empty(self):
        """Returns [] when progress has no current episode."""
        progress = self._make_progress(episode=None)
        self.assertEqual(get_eligible_transitions(progress), [])

    # ------------------------------------------------------------------
    # Progression requirement gate
    # ------------------------------------------------------------------

    def test_no_transitions_eligible_when_progression_requirement_unmet(self):
        """All transitions are blocked when a gating beat is still UNSATISFIED."""
        episode = EpisodeFactory()
        progress = self._make_progress(episode=episode)

        # One beat that has NOT reached SUCCESS yet.
        beat = BeatFactory(episode=episode, outcome=BeatOutcome.UNSATISFIED)
        EpisodeProgressionRequirementFactory(
            episode=episode, beat=beat, required_outcome=BeatOutcome.SUCCESS
        )

        # A perfectly fine transition with no routing requirements.
        TransitionFactory(source_episode=episode)

        result = get_eligible_transitions(progress)
        self.assertEqual(result, [])

    def test_transition_eligible_when_requirements_met(self):
        """Single transition is returned when all requirements are satisfied."""
        episode = EpisodeFactory()
        progress = self._make_progress(episode=episode)

        # Progression requirement: beat must be SUCCESS.
        beat = BeatFactory(episode=episode, outcome=BeatOutcome.SUCCESS)
        EpisodeProgressionRequirementFactory(
            episode=episode, beat=beat, required_outcome=BeatOutcome.SUCCESS
        )

        # A transition whose single routing req is also satisfied.
        transition = TransitionFactory(source_episode=episode)
        routing_beat = BeatFactory(episode=episode, outcome=BeatOutcome.SUCCESS)
        TransitionRequiredOutcomeFactory(
            transition=transition,
            beat=routing_beat,
            required_outcome=BeatOutcome.SUCCESS,
        )

        result = get_eligible_transitions(progress)
        self.assertEqual(result, [transition])

    def test_transition_with_no_routing_requirements_is_eligible_when_progression_met(self):
        """A transition with empty routing requirements fires when progression is met."""
        episode = EpisodeFactory()
        progress = self._make_progress(episode=episode)

        # Progression beat satisfied.
        beat = BeatFactory(episode=episode, outcome=BeatOutcome.SUCCESS)
        EpisodeProgressionRequirementFactory(
            episode=episode, beat=beat, required_outcome=BeatOutcome.SUCCESS
        )

        # Transition with zero routing requirements.
        transition = TransitionFactory(source_episode=episode)

        result = get_eligible_transitions(progress)
        self.assertEqual(result, [transition])

    # ------------------------------------------------------------------
    # Branching on beat outcome
    # ------------------------------------------------------------------

    def test_branching_on_beat_outcome_only_failure_branch_eligible(self):
        """When mission_beat.outcome=FAILURE only the failure-routed transition is eligible."""
        story = StoryFactory()
        chapter = ChapterFactory(story=story)

        source = EpisodeFactory(chapter=chapter)
        target_success = EpisodeFactory(chapter=chapter)
        target_failure = EpisodeFactory(chapter=chapter)
        progress = self._make_progress(episode=source)

        # The shared mission beat — resolved as FAILURE.
        mission_beat = BeatFactory(episode=source, outcome=BeatOutcome.FAILURE)

        # One transition gated on SUCCESS, another on FAILURE.
        success_transition = TransitionFactory(
            source_episode=source,
            target_episode=target_success,
            mode=TransitionMode.AUTO,
            order=0,
        )
        TransitionRequiredOutcomeFactory(
            transition=success_transition,
            beat=mission_beat,
            required_outcome=BeatOutcome.SUCCESS,
        )

        failure_transition = TransitionFactory(
            source_episode=source,
            target_episode=target_failure,
            mode=TransitionMode.AUTO,
            order=1,
        )
        TransitionRequiredOutcomeFactory(
            transition=failure_transition,
            beat=mission_beat,
            required_outcome=BeatOutcome.FAILURE,
        )

        result = get_eligible_transitions(progress)
        self.assertEqual(result, [failure_transition])

    def test_branching_on_beat_outcome_only_success_branch_eligible(self):
        """When mission_beat.outcome=SUCCESS only the success-routed transition is eligible."""
        story = StoryFactory()
        chapter = ChapterFactory(story=story)

        source = EpisodeFactory(chapter=chapter)
        target_success = EpisodeFactory(chapter=chapter)
        target_failure = EpisodeFactory(chapter=chapter)
        progress = self._make_progress(episode=source)

        mission_beat = BeatFactory(episode=source, outcome=BeatOutcome.SUCCESS)

        success_transition = TransitionFactory(
            source_episode=source,
            target_episode=target_success,
            mode=TransitionMode.AUTO,
            order=0,
        )
        TransitionRequiredOutcomeFactory(
            transition=success_transition,
            beat=mission_beat,
            required_outcome=BeatOutcome.SUCCESS,
        )

        failure_transition = TransitionFactory(
            source_episode=source,
            target_episode=target_failure,
            mode=TransitionMode.AUTO,
            order=1,
        )
        TransitionRequiredOutcomeFactory(
            transition=failure_transition,
            beat=mission_beat,
            required_outcome=BeatOutcome.FAILURE,
        )

        result = get_eligible_transitions(progress)
        self.assertEqual(result, [success_transition])

    # ------------------------------------------------------------------
    # Ordering
    # ------------------------------------------------------------------

    def test_eligible_transitions_ordered_by_order_then_pk(self):
        """get_eligible_transitions respects order then pk for determinism."""
        episode = EpisodeFactory()
        progress = self._make_progress(episode=episode)

        # No routing requirements, so both are eligible.
        t1 = TransitionFactory(source_episode=episode, order=2)
        t2 = TransitionFactory(source_episode=episode, order=1)
        t3 = TransitionFactory(source_episode=episode, order=1)

        result = get_eligible_transitions(progress)
        # order=1 entries before order=2; within order=1, lower pk first.
        expected = [*sorted([t2, t3], key=lambda t: t.pk), t1]
        self.assertEqual(result, expected)
