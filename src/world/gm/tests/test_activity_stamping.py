"""Tests for touch_gm_activity + activity stamping from GM verbs (#2004)."""

from django.test import TestCase

from world.gm.factories import GMProfileFactory, GMTableFactory
from world.gm.services import surrender_character_story, touch_gm_activity
from world.stories.factories import StoryFactory


class TouchGmActivityTests(TestCase):
    def test_stamps_last_active_at(self) -> None:
        gm = GMProfileFactory()
        self.assertIsNone(gm.last_active_at)
        touch_gm_activity(gm)
        gm.refresh_from_db()
        self.assertIsNotNone(gm.last_active_at)

    def test_is_idempotent_and_updates(self) -> None:
        gm = GMProfileFactory()
        touch_gm_activity(gm)
        first = gm.last_active_at
        touch_gm_activity(gm)
        gm.refresh_from_db()
        self.assertGreaterEqual(gm.last_active_at, first)


class SurrenderStampsActivityTests(TestCase):
    def test_surrender_stamps_gm_activity(self) -> None:
        gm = GMProfileFactory()
        table = GMTableFactory(gm=gm)
        story = StoryFactory(primary_table=table)
        self.assertIsNone(gm.last_active_at)
        surrender_character_story(gm, story)
        gm.refresh_from_db()
        self.assertIsNotNone(gm.last_active_at)


class GMVerbActivityStampingTests(TestCase):
    """Each GM-verb service that receives a gm_profile stamps activity (#2004)."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.stories.factories import seed_default_risk_calibrations

        seed_default_risk_calibrations()

    def test_resolve_episode_stamps_resolved_by(self) -> None:
        from world.stories.constants import (
            BeatPredicateType,
            StoryMaturity,
        )
        from world.stories.factories import (
            BeatFactory,
            ChapterFactory,
            EpisodeFactory,
            StoryFactory,
            StoryProgressFactory,
            TransitionFactory,
        )
        from world.stories.services.episodes import resolve_episode

        gm = GMProfileFactory()
        self.assertIsNone(gm.last_active_at)
        story = StoryFactory()
        chapter = ChapterFactory(story=story, is_active=True, maturity=StoryMaturity.PLOT)
        episode = EpisodeFactory(chapter=chapter)
        BeatFactory(episode=episode, predicate_type=BeatPredicateType.GM_MARKED)
        progress = StoryProgressFactory(story=story, current_episode=episode)
        transition = TransitionFactory(source_episode=episode)
        resolve_episode(progress=progress, chosen_transition=transition, resolved_by=gm)
        gm.refresh_from_db()
        self.assertIsNotNone(gm.last_active_at)

    def test_resolve_stake_by_gm_pick_stamps(self) -> None:
        from world.societies.constants import RenownRisk
        from world.stories.constants import (
            BeatPredicateType,
            StakeResolutionColumn,
            StakeSeverity,
        )
        from world.stories.factories import (
            BeatFactory,
            StakeFactory,
            StakeResolutionFactory,
        )
        from world.stories.services.stake_resolution import resolve_stake_by_gm_pick

        gm = GMProfileFactory()
        self.assertIsNone(gm.last_active_at)
        beat = BeatFactory(
            risk=RenownRisk.HIGH,
            target_level=4,
            predicate_type=BeatPredicateType.OUTCOME_TIER,
        )
        stake = StakeFactory(beat=beat, severity=StakeSeverity.DIRE)
        StakeResolutionFactory(stake=stake, column=StakeResolutionColumn.WIN)
        StakeResolutionFactory(stake=stake, column=StakeResolutionColumn.LOSS)
        resolve_stake_by_gm_pick(stake, column=StakeResolutionColumn.WIN, gm_profile=gm)
        gm.refresh_from_db()
        self.assertIsNotNone(gm.last_active_at)
