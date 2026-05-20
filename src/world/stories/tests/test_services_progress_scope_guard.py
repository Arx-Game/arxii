from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.stories.constants import StoryScope
from world.stories.exceptions import StoryNotAssignedError
from world.stories.factories import StoryFactory
from world.stories.services.progress import create_character_progress


class ScopeGuardTests(TestCase):
    def test_unassigned_story_rejects_character_progress(self) -> None:
        story = StoryFactory(scope=StoryScope.UNASSIGNED, character_sheet=None)
        sheet = CharacterSheetFactory()
        with self.assertRaises(StoryNotAssignedError):
            create_character_progress(story=story, character_sheet=sheet)
