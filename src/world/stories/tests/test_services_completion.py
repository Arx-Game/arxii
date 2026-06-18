"""Tests for complete_story: conclude a story + honestly foreclose in-flight progress."""

from django.test import TestCase

from world.stories.constants import ProgressStatus, StoryScope
from world.stories.factories import (
    GlobalStoryProgressFactory,
    GroupStoryProgressFactory,
    StoryFactory,
    StoryProgressFactory,
)
from world.stories.services.completion import complete_story
from world.stories.types import StoryStatus


class CompleteStoryTests(TestCase):
    def test_sets_completed_status_and_timestamp(self):
        story = StoryFactory(status=StoryStatus.ACTIVE)
        complete_story(story=story)
        story.refresh_from_db()
        self.assertEqual(story.status, StoryStatus.COMPLETED)
        self.assertIsNotNone(story.completed_at)

    def test_idempotent(self):
        story = StoryFactory(status=StoryStatus.ACTIVE)
        complete_story(story=story)
        story.refresh_from_db()
        first_ts = story.completed_at
        complete_story(story=story)
        story.refresh_from_db()
        self.assertEqual(story.completed_at, first_ts)

    def test_in_flight_group_progress_foreclosed(self):
        story = StoryFactory(status=StoryStatus.ACTIVE, scope=StoryScope.GROUP)
        progress = GroupStoryProgressFactory(
            story=story, status=ProgressStatus.ACTIVE, is_active=True
        )
        complete_story(story=story)
        progress.refresh_from_db()
        self.assertEqual(progress.status, ProgressStatus.FORECLOSED)
        self.assertFalse(progress.is_active)

    def test_in_flight_character_progress_foreclosed(self):
        story = StoryFactory(status=StoryStatus.ACTIVE, scope=StoryScope.CHARACTER)
        progress = StoryProgressFactory(story=story, status=ProgressStatus.RESTING, is_active=True)
        complete_story(story=story)
        progress.refresh_from_db()
        self.assertEqual(progress.status, ProgressStatus.FORECLOSED)
        self.assertFalse(progress.is_active)

    def test_in_flight_global_progress_foreclosed(self):
        story = StoryFactory(status=StoryStatus.ACTIVE, scope=StoryScope.GLOBAL)
        progress = GlobalStoryProgressFactory(
            story=story, status=ProgressStatus.ACTIVE, is_active=True
        )
        complete_story(story=story)
        progress.refresh_from_db()
        self.assertEqual(progress.status, ProgressStatus.FORECLOSED)
        self.assertFalse(progress.is_active)

    def test_already_completed_progress_preserved(self):
        story = StoryFactory(status=StoryStatus.ACTIVE, scope=StoryScope.GROUP)
        progress = GroupStoryProgressFactory(
            story=story, status=ProgressStatus.COMPLETED, is_active=False
        )
        complete_story(story=story)
        progress.refresh_from_db()
        self.assertEqual(progress.status, ProgressStatus.COMPLETED)
