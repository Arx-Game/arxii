"""Tests for compute_story_status_line FORECLOSED branch.

A foreclosed record must surface an honest nudge (unresolved) or closure line
(resolved) — never the ACTIVE fall-through copy.
"""

from django.test import TestCase
from django.utils import timezone

from world.stories.constants import ProgressStatus, StoryScope
from world.stories.factories import StoryFactory, StoryProgressFactory
from world.stories.services.dashboards import compute_story_status_line
from world.stories.types import StoryStatus


class ComputeStoryStatusLineForeclosedTests(TestCase):
    def _foreclosed_progress(self, *, resolved_at=None):
        story = StoryFactory(status=StoryStatus.COMPLETED, scope=StoryScope.CHARACTER)
        return StoryProgressFactory(
            story=story,
            status=ProgressStatus.FORECLOSED,
            is_active=False,
            resolved_at=resolved_at,
        )

    def test_foreclosed_unresolved_returns_nudge_copy(self):
        progress = self._foreclosed_progress(resolved_at=None)
        line = compute_story_status_line(progress)
        self.assertIn("unresolved", line.lower())
        # Must not fall through to the ACTIVE copy.
        self.assertNotIn("being prepared", line.lower())
        self.assertNotIn("continues", line.lower())

    def test_foreclosed_resolved_returns_closure_copy(self):
        progress = self._foreclosed_progress(resolved_at=timezone.now())
        line = compute_story_status_line(progress)
        self.assertIn("closed", line.lower())
        # Honest: never claims completion.
        self.assertNotIn("completed", line.lower())
        self.assertNotIn("continues", line.lower())

    def test_foreclosed_never_returns_active_copy(self):
        progress = self._foreclosed_progress(resolved_at=None)
        line = compute_story_status_line(progress)
        self.assertNotIn("continues", line.lower())
