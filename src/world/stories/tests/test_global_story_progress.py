from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TransactionTestCase
from evennia.utils.test_resources import EvenniaTestCase

from world.stories.constants import StoryScope
from world.stories.factories import GlobalStoryProgressFactory, StoryFactory


class GlobalStoryProgressModelTests(EvenniaTestCase):
    """Unit tests for GlobalStoryProgress GLOBAL-scope singleton progress model."""

    def test_progress_links_to_story(self) -> None:
        """GlobalStoryProgress correctly stores the OneToOne story FK."""
        progress = GlobalStoryProgressFactory()
        self.assertIsNotNone(progress.story)
        self.assertTrue(progress.is_active)
        self.assertEqual(progress.story.scope, StoryScope.GLOBAL)
        # OneToOne reverse accessor works.
        self.assertEqual(progress.story.global_progress, progress)

    def test_global_scope_required(self) -> None:
        """GlobalStoryProgress with a non-GLOBAL-scope story raises ValidationError."""
        for scope in (StoryScope.CHARACTER, StoryScope.GROUP):
            with self.subTest(scope=scope):
                story = StoryFactory(scope=scope)
                with self.assertRaises(ValidationError) as ctx:
                    GlobalStoryProgressFactory(story=story)
                self.assertIn("story", ctx.exception.message_dict)

    def test_frontier_state(self) -> None:
        """current_episode=None is valid (story at frontier / not started)."""
        progress = GlobalStoryProgressFactory(current_episode=None)
        self.assertIsNone(progress.current_episode)

    def test_str_with_frontier(self) -> None:
        """__str__ shows '(frontier)' when current_episode is None."""
        progress = GlobalStoryProgressFactory(current_episode=None)
        result = str(progress)
        self.assertIn(progress.story.title, result)
        self.assertIn("(frontier)", result)


class GlobalStoryProgressUniqueConstraintTests(TransactionTestCase):
    """Tests requiring TransactionTestCase to catch DB-level unique violations."""

    def test_only_one_per_story(self) -> None:
        """OneToOne on story prevents creating a second GlobalStoryProgress for the same story."""
        story = StoryFactory(scope=StoryScope.GLOBAL)
        GlobalStoryProgressFactory(story=story)
        with self.assertRaises(IntegrityError):
            GlobalStoryProgressFactory(story=story)
