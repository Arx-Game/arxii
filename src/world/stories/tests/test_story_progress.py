from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TransactionTestCase
from evennia.utils.test_resources import EvenniaTestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.stories.constants import StoryScope
from world.stories.factories import EpisodeFactory, StoryFactory, StoryProgressFactory


class StoryProgressModelTests(EvenniaTestCase):
    """Unit tests for the StoryProgress per-character progress pointer model."""

    def test_progress_links_story_to_character_sheet(self) -> None:
        """StoryProgress correctly stores story and character_sheet FKs."""
        progress = StoryProgressFactory()
        self.assertIsNotNone(progress.story)
        self.assertIsNotNone(progress.character_sheet)
        self.assertTrue(progress.is_active)

    def test_progress_tracks_current_episode(self) -> None:
        """current_episode round-trips through the database."""
        progress = StoryProgressFactory()
        # Create an episode and attach it
        episode = EpisodeFactory()
        progress.current_episode = episode
        progress.save()
        progress.refresh_from_db()
        self.assertEqual(progress.current_episode, episode)

    def test_progress_null_episode_is_frontier(self) -> None:
        """current_episode defaults to None (frontier / not started)."""
        progress = StoryProgressFactory(current_episode=None)
        self.assertIsNone(progress.current_episode)

    def test_progress_str_with_episode(self) -> None:
        """__str__ includes story title and episode title."""
        episode = EpisodeFactory()
        progress = StoryProgressFactory(current_episode=episode)
        result = str(progress)
        self.assertIn(progress.story.title, result)
        self.assertIn(episode.title, result)

    def test_progress_str_without_episode(self) -> None:
        """__str__ shows '(frontier)' when current_episode is None."""
        progress = StoryProgressFactory(current_episode=None)
        self.assertIn("(frontier)", str(progress))


class StoryProgressUniqueConstraintTests(TransactionTestCase):
    """Tests that require TransactionTestCase to catch DB-level unique violations."""

    def test_one_progress_per_story_per_character(self) -> None:
        """UniqueConstraint prevents duplicate (story, character_sheet) pairs."""
        story = StoryFactory()
        sheet = CharacterSheetFactory()
        StoryProgressFactory(story=story, character_sheet=sheet)
        with self.assertRaises(IntegrityError):
            StoryProgressFactory(story=story, character_sheet=sheet)


class StoryProgressCleanInvariantTests(EvenniaTestCase):
    """Tests for StoryProgress.clean() CHARACTER-scope invariant enforcement."""

    def test_character_scope_progress_must_match_story_character_sheet(self) -> None:
        """StoryProgress for a CHARACTER-scope story must use the story's own character_sheet."""
        sheet_a = CharacterSheetFactory()
        sheet_b = CharacterSheetFactory()
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet_a)
        with self.assertRaises(ValidationError):
            StoryProgressFactory(story=story, character_sheet=sheet_b)

    def test_character_scope_progress_allows_matching_character_sheet(self) -> None:
        """StoryProgress for a CHARACTER-scope story succeeds when sheets match."""
        sheet = CharacterSheetFactory()
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet)
        progress = StoryProgressFactory(story=story, character_sheet=sheet)
        self.assertEqual(progress.character_sheet, sheet)

    def test_character_scope_without_owner_wired_allows_any_sheet(self) -> None:
        """If Story.character_sheet is None, the invariant is skipped (deferred to service)."""
        sheet = CharacterSheetFactory()
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=None)
        # Should not raise.
        progress = StoryProgressFactory(story=story, character_sheet=sheet)
        self.assertEqual(progress.character_sheet, sheet)
