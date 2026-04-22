from django.db import IntegrityError
from django.test import TestCase, TransactionTestCase

from world.stories.constants import BeatOutcome
from world.stories.factories import (
    BeatFactory,
    EpisodeFactory,
    EpisodeProgressionRequirementFactory,
    TransitionFactory,
    TransitionRequiredOutcomeFactory,
)


class RequirementTests(TestCase):
    def test_progression_requirement_links_episode_to_beat(self):
        episode = EpisodeFactory()
        beat = BeatFactory(episode=episode)
        req = EpisodeProgressionRequirementFactory(
            episode=episode,
            beat=beat,
            required_outcome=BeatOutcome.SUCCESS,
        )
        self.assertEqual(req.episode, episode)
        self.assertEqual(req.beat, beat)
        self.assertEqual(req.required_outcome, BeatOutcome.SUCCESS)

    def test_transition_required_outcome_links_to_beat(self):
        transition = TransitionFactory()
        beat = BeatFactory(episode=transition.source_episode)
        req = TransitionRequiredOutcomeFactory(
            transition=transition,
            beat=beat,
            required_outcome=BeatOutcome.FAILURE,
        )
        self.assertEqual(req.required_outcome, BeatOutcome.FAILURE)


class RequirementUniqueConstraintTests(TransactionTestCase):
    def test_progression_requirement_unique_per_episode_beat(self):
        episode = EpisodeFactory()
        beat = BeatFactory(episode=episode)
        EpisodeProgressionRequirementFactory(episode=episode, beat=beat)
        with self.assertRaises(IntegrityError):
            EpisodeProgressionRequirementFactory(episode=episode, beat=beat)

    def test_transition_required_outcome_unique_per_transition_beat(self):
        transition = TransitionFactory()
        beat = BeatFactory(episode=transition.source_episode)
        TransitionRequiredOutcomeFactory(transition=transition, beat=beat)
        with self.assertRaises(IntegrityError):
            TransitionRequiredOutcomeFactory(transition=transition, beat=beat)
