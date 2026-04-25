"""Gate 10.4 — protagonism-locked characters cannot participate in stories."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.exceptions import ProtagonismLockedError
from world.magic.factories import ResonanceFactory, with_corruption_at_stage
from world.stories.factories import StoryFactory
from world.stories.services.participation import create_story_participation


class ProtagonismLockStoryParticipationTests(TestCase):
    """create_story_participation raises ProtagonismLockedError for subsumed characters."""

    def _make_subsumed_character(self):
        """Return an ObjectDB character whose sheet is at corruption stage 5."""
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        with_corruption_at_stage(sheet, resonance, stage=5)
        sheet.__dict__.pop("is_protagonism_locked", None)
        return sheet.character

    def test_subsumed_character_cannot_join_story(self) -> None:
        character = self._make_subsumed_character()
        story = StoryFactory()

        with self.assertRaises(ProtagonismLockedError):
            create_story_participation(
                story=story,
                character=character,
                participation_level="optional",
            )

    def test_normal_character_can_join_story(self) -> None:
        """Sanity check: non-locked characters can participate normally."""
        sheet = CharacterSheetFactory()
        story = StoryFactory()

        from world.stories.models import StoryParticipation

        participation = create_story_participation(
            story=story,
            character=sheet.character,
            participation_level="optional",
        )

        self.assertIsInstance(participation, StoryParticipation)
        self.assertEqual(participation.character, sheet.character)
