"""Tests for story-critical NPC protection in peril resolution (#1874)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.stories.factories import StoryFactory
from world.stories.models import StoryNPCDependency
from world.stories.types import StoryStatus
from world.vitals.peril_resolution import death_is_permitted


class StoryCriticalPerilTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.npc_sheet = CharacterSheetFactory()
        cls.npc_obj = cls.npc_sheet.character
        # Create a non-PC attacker (an NPC without db_account)
        cls.npc_attacker = CharacterSheetFactory().character
        cls.story = StoryFactory(status=StoryStatus.ACTIVE)

    def test_story_critical_npc_death_not_permitted(self):
        StoryNPCDependency.objects.create(story=self.story, npc_sheet=self.npc_sheet)
        result = death_is_permitted(
            victim_sheet=self.npc_sheet,
            source_character=self.npc_attacker,
        )
        self.assertFalse(result)

    def test_non_story_critical_npc_death_permitted_for_npc_source(self):
        result = death_is_permitted(
            victim_sheet=self.npc_sheet,
            source_character=self.npc_attacker,
        )
        self.assertTrue(result)
