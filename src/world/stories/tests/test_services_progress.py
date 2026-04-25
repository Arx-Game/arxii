"""Tests for world.stories.services.progress scope-polymorphic helpers."""

from evennia.utils.test_resources import EvenniaTestCase

from world.achievements.factories import AchievementFactory, CharacterAchievementFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.factories import GMTableFactory
from world.stories.constants import BeatOutcome, BeatPredicateType, StoryScope
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    GlobalStoryProgressFactory,
    GroupStoryProgressFactory,
    StoryFactory,
    StoryProgressFactory,
)
from world.stories.models import BeatCompletion
from world.stories.services.progress import (
    advance_progress_to_episode,
    create_character_progress,
    create_global_progress,
    create_group_progress,
    get_active_progress_for_story,
)


class GetActiveProgressForStoryTests(EvenniaTestCase):
    """Tests for get_active_progress_for_story() dispatching on scope."""

    def test_get_active_progress_for_character_story(self) -> None:
        """Returns the active StoryProgress for a CHARACTER-scope story."""
        progress = StoryProgressFactory(is_active=True)
        result = get_active_progress_for_story(progress.story)
        self.assertEqual(result, progress)

    def test_get_active_progress_for_group_story(self) -> None:
        """Returns the active GroupStoryProgress for a GROUP-scope story."""
        progress = GroupStoryProgressFactory(is_active=True)
        result = get_active_progress_for_story(progress.story)
        self.assertEqual(result, progress)

    def test_get_active_progress_for_global_story(self) -> None:
        """Returns the GlobalStoryProgress for a GLOBAL-scope story."""
        progress = GlobalStoryProgressFactory(is_active=True)
        result = get_active_progress_for_story(progress.story)
        self.assertEqual(result, progress)

    def test_get_active_progress_returns_none_when_no_progress_character(self) -> None:
        """Returns None when no StoryProgress exists for a CHARACTER-scope story."""
        story = StoryFactory(scope=StoryScope.CHARACTER)
        result = get_active_progress_for_story(story)
        self.assertIsNone(result)

    def test_get_active_progress_returns_none_when_no_progress_group(self) -> None:
        """Returns None when no GroupStoryProgress exists for a GROUP-scope story."""
        story = StoryFactory(scope=StoryScope.GROUP)
        result = get_active_progress_for_story(story)
        self.assertIsNone(result)

    def test_get_active_progress_returns_none_when_no_progress_global(self) -> None:
        """Returns None when no GlobalStoryProgress exists for a GLOBAL-scope story."""
        story = StoryFactory(scope=StoryScope.GLOBAL)
        result = get_active_progress_for_story(story)
        self.assertIsNone(result)

    def test_get_active_progress_skips_inactive_character(self) -> None:
        """Returns None when the only StoryProgress is inactive."""
        progress = StoryProgressFactory(is_active=False)
        result = get_active_progress_for_story(progress.story)
        self.assertIsNone(result)

    def test_get_active_progress_skips_inactive_group(self) -> None:
        """Returns None when the only GroupStoryProgress is inactive."""
        progress = GroupStoryProgressFactory(is_active=False)
        result = get_active_progress_for_story(progress.story)
        self.assertIsNone(result)


class AdvanceProgressToEpisodeTests(EvenniaTestCase):
    """Tests for advance_progress_to_episode() working on all three progress types."""

    def test_advance_character_progress_to_episode(self) -> None:
        """Updates current_episode on StoryProgress."""
        progress = StoryProgressFactory(current_episode=None)
        episode = EpisodeFactory()
        advance_progress_to_episode(progress, episode)
        progress.refresh_from_db()
        self.assertEqual(progress.current_episode, episode)

    def test_advance_group_progress_to_episode(self) -> None:
        """Updates current_episode on GroupStoryProgress."""
        progress = GroupStoryProgressFactory(current_episode=None)
        episode = EpisodeFactory()
        advance_progress_to_episode(progress, episode)
        progress.refresh_from_db()
        self.assertEqual(progress.current_episode, episode)

    def test_advance_global_progress_to_episode(self) -> None:
        """Updates current_episode on GlobalStoryProgress."""
        progress = GlobalStoryProgressFactory(current_episode=None)
        episode = EpisodeFactory()
        advance_progress_to_episode(progress, episode)
        progress.refresh_from_db()
        self.assertEqual(progress.current_episode, episode)

    def test_advance_progress_to_none_frontier(self) -> None:
        """Passing target_episode=None sets current_episode to None (frontier case)."""
        episode = EpisodeFactory()
        progress = StoryProgressFactory(current_episode=episode)
        advance_progress_to_episode(progress, None)
        progress.refresh_from_db()
        self.assertIsNone(progress.current_episode)

    def test_advance_group_progress_to_none_frontier(self) -> None:
        """Frontier case works for GroupStoryProgress too."""
        episode = EpisodeFactory()
        progress = GroupStoryProgressFactory(current_episode=episode)
        advance_progress_to_episode(progress, None)
        progress.refresh_from_db()
        self.assertIsNone(progress.current_episode)


class CreateCharacterProgressSnapshotTests(EvenniaTestCase):
    """create_character_progress must evaluate auto-beats at creation time."""

    def test_retroactive_achievement_beat_auto_satisfies(self) -> None:
        sheet = CharacterSheetFactory()
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet)
        episode = EpisodeFactory(chapter=ChapterFactory(story=story))
        achievement = AchievementFactory()
        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.ACHIEVEMENT_HELD,
            required_achievement=achievement,
            outcome=BeatOutcome.UNSATISFIED,
        )
        CharacterAchievementFactory(character_sheet=sheet, achievement=achievement)

        progress = create_character_progress(
            story=story,
            character_sheet=sheet,
            current_episode=episode,
        )

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.SUCCESS)
        self.assertTrue(
            BeatCompletion.objects.filter(beat=beat, character_sheet=sheet).exists(),
        )
        self.assertEqual(progress.current_episode, episode)

    def test_no_episode_just_creates_progress(self) -> None:
        sheet = CharacterSheetFactory()
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet)
        progress = create_character_progress(story=story, character_sheet=sheet)
        self.assertIsNone(progress.current_episode)


class CreateGroupProgressSnapshotTests(EvenniaTestCase):
    def test_creates_and_evaluates(self) -> None:
        story = StoryFactory(scope=StoryScope.GROUP, character_sheet=None)
        table = GMTableFactory()
        progress = create_group_progress(story=story, gm_table=table)
        self.assertIsNotNone(progress.pk)
        self.assertEqual(progress.gm_table, table)


class CreateGlobalProgressSnapshotTests(EvenniaTestCase):
    def test_creates_and_evaluates(self) -> None:
        story = StoryFactory(scope=StoryScope.GLOBAL, character_sheet=None)
        episode = EpisodeFactory(chapter=ChapterFactory(story=story))
        progress = create_global_progress(story=story, current_episode=episode)
        self.assertIsNotNone(progress.pk)
        self.assertEqual(progress.current_episode, episode)
