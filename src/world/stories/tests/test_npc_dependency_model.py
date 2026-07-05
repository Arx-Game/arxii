"""Tests for the StoryNPCDependency model (#1874)."""

from django.db import IntegrityError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.stories.factories import BeatFactory, StoryFactory
from world.stories.models import StoryNPCDependency


class StoryNPCDependencyModelTests(TestCase):
    def test_story_level_dependency_defaults(self):
        sheet = CharacterSheetFactory()
        story = StoryFactory()
        dep = StoryNPCDependency.objects.create(story=story, npc_sheet=sheet)
        self.assertTrue(dep.is_active)
        self.assertIsNone(dep.beat)
        self.assertEqual(dep.notes, "")
        self.assertIsNotNone(dep.created_at)

    def test_beat_level_dependency(self):
        sheet = CharacterSheetFactory()
        story = StoryFactory()
        beat = BeatFactory(episode__chapter__story=story)
        dep = StoryNPCDependency.objects.create(story=story, npc_sheet=sheet, beat=beat)
        self.assertEqual(dep.beat, beat)

    def test_unique_together_story_npc_sheet(self):
        sheet = CharacterSheetFactory()
        story = StoryFactory()
        StoryNPCDependency.objects.create(story=story, npc_sheet=sheet)
        with self.assertRaises(IntegrityError):
            StoryNPCDependency.objects.create(story=story, npc_sheet=sheet)

    def test_same_npc_different_stories_allowed(self):
        sheet = CharacterSheetFactory()
        story_a = StoryFactory()
        story_b = StoryFactory()
        dep_a = StoryNPCDependency.objects.create(story=story_a, npc_sheet=sheet)
        dep_b = StoryNPCDependency.objects.create(story=story_b, npc_sheet=sheet)
        self.assertNotEqual(dep_a.pk, dep_b.pk)
