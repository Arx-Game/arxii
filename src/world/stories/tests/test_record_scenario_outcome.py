"""record_scenario_outcome writes outcome, tier and option key (#3565)."""

from django.test import TestCase

from world.stories.constants import BeatOutcome, BeatPredicateType
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    StoryFactory,
    StoryProgressFactory,
)
from world.stories.services.beats import record_scenario_outcome
from world.traits.factories import CheckOutcomeFactory
from world.traits.models import CheckOutcome


class RecordScenarioOutcomeTests(TestCase):
    def setUp(self) -> None:
        story = StoryFactory()
        episode = EpisodeFactory(chapter=ChapterFactory(story=story))
        self.progress = StoryProgressFactory(story=story, current_episode=episode)
        self.beat = BeatFactory(episode=episode, predicate_type=BeatPredicateType.OUTCOME_TIER)

    def test_tierless_failure_records_key_and_no_tier(self) -> None:
        completion = record_scenario_outcome(
            progress=self.progress,
            beat=self.beat,
            outcome=BeatOutcome.FAILURE,
            outcome_tier=None,
            outcome_key="walk-away",
        )
        self.beat.refresh_from_db()
        self.assertEqual(self.beat.outcome, BeatOutcome.FAILURE)
        self.assertEqual(self.beat.outcome_key, "walk-away")
        self.assertEqual(completion.outcome_key, "walk-away")
        self.assertIsNone(completion.outcome_tier)

    def test_tier_recorded_when_given(self) -> None:
        tier = CheckOutcome.objects.order_by("-success_level").first()
        if tier is None:
            tier = CheckOutcomeFactory(success_level=4)
        completion = record_scenario_outcome(
            progress=self.progress,
            beat=self.beat,
            outcome=BeatOutcome.SUCCESS,
            outcome_tier=tier,
            outcome_key="negotiate",
        )
        self.assertEqual(completion.outcome_tier_id, tier.pk)

    def test_gm_marked_beat_rejected(self) -> None:
        beat = BeatFactory(episode=self.beat.episode, predicate_type=BeatPredicateType.GM_MARKED)
        with self.assertRaises(ValueError):
            record_scenario_outcome(
                progress=self.progress,
                beat=beat,
                outcome=BeatOutcome.SUCCESS,
                outcome_tier=None,
                outcome_key="x",
            )
