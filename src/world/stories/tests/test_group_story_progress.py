from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TransactionTestCase
from evennia.utils.test_resources import EvenniaTestCase

from world.gm.factories import GMTableFactory
from world.stories.constants import StoryScope
from world.stories.factories import (
    EpisodeFactory,
    GroupStoryProgressFactory,
    StoryFactory,
)


class GroupStoryProgressModelTests(EvenniaTestCase):
    """Unit tests for GroupStoryProgress GROUP-scope progress pointer model."""

    def test_progress_links_story_to_gm_table(self) -> None:
        """GroupStoryProgress correctly stores story and gm_table FKs."""
        progress = GroupStoryProgressFactory()
        self.assertIsNotNone(progress.story)
        self.assertIsNotNone(progress.gm_table)
        self.assertTrue(progress.is_active)
        self.assertEqual(progress.story.scope, StoryScope.GROUP)

    def test_progress_tracks_current_episode(self) -> None:
        """current_episode round-trips through the database."""
        progress = GroupStoryProgressFactory()
        episode = EpisodeFactory()
        progress.current_episode = episode
        progress.save(update_fields=["current_episode", "last_advanced_at"])
        progress.refresh_from_db()
        self.assertEqual(progress.current_episode, episode)

    def test_group_scope_required(self) -> None:
        """GroupStoryProgress with a non-GROUP-scope story raises ValidationError."""
        character_story = StoryFactory(scope=StoryScope.CHARACTER)
        gm_table = GMTableFactory()
        with self.assertRaises(ValidationError) as ctx:
            GroupStoryProgressFactory(story=character_story, gm_table=gm_table)
        self.assertIn("story", ctx.exception.message_dict)

    def test_frontier_state(self) -> None:
        """current_episode=None is valid (story at frontier / not started)."""
        progress = GroupStoryProgressFactory(current_episode=None)
        self.assertIsNone(progress.current_episode)

    def test_str_with_episode(self) -> None:
        """__str__ includes gm_table name, story title, and episode title."""
        episode = EpisodeFactory()
        progress = GroupStoryProgressFactory(current_episode=episode)
        result = str(progress)
        self.assertIn(progress.gm_table.name, result)
        self.assertIn(progress.story.title, result)
        self.assertIn(episode.title, result)

    def test_str_without_episode(self) -> None:
        """__str__ shows '(frontier)' when current_episode is None."""
        progress = GroupStoryProgressFactory(current_episode=None)
        self.assertIn("(frontier)", str(progress))


class GroupStoryProgressUniqueConstraintTests(TransactionTestCase):
    """Tests requiring TransactionTestCase to catch DB-level unique violations."""

    def test_unique_per_story_per_table(self) -> None:
        """UniqueConstraint prevents duplicate (story, gm_table) pairs."""
        story = StoryFactory(scope=StoryScope.GROUP)
        gm_table = GMTableFactory()
        GroupStoryProgressFactory(story=story, gm_table=gm_table)
        with self.assertRaises(IntegrityError):
            GroupStoryProgressFactory(story=story, gm_table=gm_table)
