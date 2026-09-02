"""StoryScenario link + outcome_key columns + routing-key clean rules (#3565)."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from world.stories.constants import BeatOutcome, BeatPredicateType, StakeResolutionColumn
from world.stories.factories import (
    BeatFactory,
    EpisodeFactory,
    StakeFactory,
    StoryFactory,
    StoryScenarioFactory,
    TransitionFactory,
)
from world.stories.models import Beat, StoryScenario, TransitionRequiredOutcome


class StoryScenarioTests(TestCase):
    def test_template_reverse_accessor_names_the_story(self) -> None:
        link = StoryScenarioFactory()
        self.assertEqual(link.template.story_scenario.story_id, link.story_id)
        self.assertIn(link, list(link.story.scenarios.all()))

    def test_a_template_belongs_to_at_most_one_story(self) -> None:
        link = StoryScenarioFactory()
        with self.assertRaises(IntegrityError):
            StoryScenario.objects.create(story=StoryFactory(), template=link.template)


class BeatDefaultsTests(TestCase):
    def test_new_beat_defaults_to_outcome_tier(self) -> None:
        beat = Beat.objects.create(episode=EpisodeFactory(), internal_description="x")
        self.assertEqual(beat.predicate_type, BeatPredicateType.OUTCOME_TIER)
        self.assertEqual(beat.outcome_key, "")


class RoutingKeyCleanTests(TestCase):
    def test_key_allowed_on_beat_level_row(self) -> None:
        beat = BeatFactory()
        transition = TransitionFactory(source_episode=beat.episode)
        row = TransitionRequiredOutcome(
            transition=transition,
            beat=beat,
            required_outcome=BeatOutcome.SUCCESS,
            required_outcome_key="negotiate",
        )
        row.full_clean()  # does not raise

    def test_key_rejected_on_stake_level_row(self) -> None:
        beat = BeatFactory()
        transition = TransitionFactory(source_episode=beat.episode)
        stake = StakeFactory(beat=beat)
        row = TransitionRequiredOutcome(
            transition=transition,
            beat=beat,
            stake=stake,
            required_stake_column=StakeResolutionColumn.WIN,
            required_outcome_key="negotiate",
        )
        with self.assertRaises(ValidationError) as ctx:
            row.full_clean()
        self.assertIn("required_outcome_key", ctx.exception.message_dict)
