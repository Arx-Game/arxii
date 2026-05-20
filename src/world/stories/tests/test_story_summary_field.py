# src/world/stories/tests/test_story_summary_field.py
from django.test import TestCase

from world.stories.factories import StoryFactory


class StorySummaryFieldTests(TestCase):
    def test_story_has_blank_summary_default(self):
        s = StoryFactory()
        self.assertEqual(s.summary, "")

    def test_summary_is_persisted(self):
        s = StoryFactory()
        s.summary = "The Story So Far text"
        s.save()
        s.refresh_from_db()
        self.assertEqual(s.summary, "The Story So Far text")
