from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.stories.constants import StoryScope
from world.stories.factories import EraFactory, StoryFactory


class StoryExtensionTests(TestCase):
    def test_story_defaults_to_character_scope(self) -> None:
        story = StoryFactory()
        self.assertEqual(story.scope, StoryScope.CHARACTER)

    def test_character_scope_requires_character_sheet(self) -> None:
        sheet = CharacterSheetFactory()
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet)
        self.assertEqual(story.character_sheet, sheet)

    def test_story_records_era_of_creation(self) -> None:
        era = EraFactory()
        story = StoryFactory(created_in_era=era)
        self.assertEqual(story.created_in_era, era)
