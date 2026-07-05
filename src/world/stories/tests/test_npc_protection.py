"""Tests for is_death_prevented_by_story (#1874)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.stories.constants import BeatOutcome
from world.stories.factories import BeatFactory, StoryFactory, StoryParticipationFactory
from world.stories.models import StoryNPCDependency
from world.stories.npc_protection import is_death_prevented_by_story
from world.stories.types import StoryStatus


class IsDeathPreventedByStoryTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.npc_sheet = CharacterSheetFactory()
        cls.npc_obj = cls.npc_sheet.character
        cls.attacker_sheet = CharacterSheetFactory()
        cls.attacker_obj = cls.attacker_sheet.character
        cls.story = StoryFactory(status=StoryStatus.ACTIVE)

    def test_no_dependencies_death_permitted(self):
        result = is_death_prevented_by_story(self.npc_sheet, self.attacker_obj)
        self.assertFalse(result)

    def test_story_level_dep_non_participant_prevented(self):
        StoryNPCDependency.objects.create(story=self.story, npc_sheet=self.npc_sheet)
        result = is_death_prevented_by_story(self.npc_sheet, self.attacker_obj)
        self.assertTrue(result)

    def test_story_level_dep_participant_permitted(self):
        StoryNPCDependency.objects.create(story=self.story, npc_sheet=self.npc_sheet)
        StoryParticipationFactory(story=self.story, character=self.attacker_obj)
        result = is_death_prevented_by_story(self.npc_sheet, self.attacker_obj)
        self.assertFalse(result)

    def test_inactive_story_protection_lifted(self):
        StoryNPCDependency.objects.create(story=self.story, npc_sheet=self.npc_sheet)
        self.story.status = StoryStatus.COMPLETED
        self.story.save(update_fields=["status"])
        result = is_death_prevented_by_story(self.npc_sheet, self.attacker_obj)
        self.assertFalse(result)

    def test_inactive_dependency_protection_lifted(self):
        dep = StoryNPCDependency.objects.create(story=self.story, npc_sheet=self.npc_sheet)
        dep.is_active = False
        dep.save(update_fields=["is_active"])
        result = is_death_prevented_by_story(self.npc_sheet, self.attacker_obj)
        self.assertFalse(result)

    def test_attacker_none_prevented(self):
        StoryNPCDependency.objects.create(story=self.story, npc_sheet=self.npc_sheet)
        result = is_death_prevented_by_story(self.npc_sheet, None)
        self.assertTrue(result)

    def test_beat_level_dep_unsatisfied_prevented(self):
        beat = BeatFactory(episode__chapter__story=self.story)
        StoryNPCDependency.objects.create(story=self.story, npc_sheet=self.npc_sheet, beat=beat)
        result = is_death_prevented_by_story(self.npc_sheet, self.attacker_obj)
        self.assertTrue(result)

    def test_beat_level_dep_resolved_protection_lifted(self):
        beat = BeatFactory(episode__chapter__story=self.story)
        StoryNPCDependency.objects.create(story=self.story, npc_sheet=self.npc_sheet, beat=beat)
        beat.outcome = BeatOutcome.SUCCESS
        beat.save(update_fields=["outcome"])
        result = is_death_prevented_by_story(self.npc_sheet, self.attacker_obj)
        self.assertFalse(result)

    def test_multi_story_attacker_in_one_not_other_prevented(self):
        story_b = StoryFactory(status=StoryStatus.ACTIVE)
        StoryNPCDependency.objects.create(story=self.story, npc_sheet=self.npc_sheet)
        StoryNPCDependency.objects.create(story=story_b, npc_sheet=self.npc_sheet)
        StoryParticipationFactory(story=self.story, character=self.attacker_obj)
        # Attacker is in story A but NOT story B
        result = is_death_prevented_by_story(self.npc_sheet, self.attacker_obj)
        self.assertTrue(result)

    def test_multi_story_attacker_in_all_permitted(self):
        story_b = StoryFactory(status=StoryStatus.ACTIVE)
        StoryNPCDependency.objects.create(story=self.story, npc_sheet=self.npc_sheet)
        StoryNPCDependency.objects.create(story=story_b, npc_sheet=self.npc_sheet)
        StoryParticipationFactory(story=self.story, character=self.attacker_obj)
        StoryParticipationFactory(story=story_b, character=self.attacker_obj)
        result = is_death_prevented_by_story(self.npc_sheet, self.attacker_obj)
        self.assertFalse(result)
