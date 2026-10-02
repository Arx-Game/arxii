"""The Audere surge and the chosen ultimate as narratable events (#4101 Task 7)."""

from django.test import TestCase

from evennia_extensions.factories import AccountFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.constants import GMPromptKind
from world.gm.models import GMPrompt
from world.magic.audere import _announce_surge
from world.magic.factories import AudereThresholdFactory, CharacterSurgeTextFactory
from world.scenes.constants import InteractionMode
from world.scenes.factories import SceneFactory, SceneGMParticipationFactory
from world.scenes.models import Interaction


def _placed_sheet():
    """A sheet whose character stands in its own room with its own active scene.

    Factory characters default to location=None, and ``active_for_room(None)``
    matches EVERY location-less active scene, so ``.first()`` would be arbitrary
    once a class creates more than one. A room per test makes the scene unambiguous.
    """
    room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
    sheet = CharacterSheetFactory()
    sheet.character.location = room
    sheet.character.save()
    return sheet, SceneFactory(location=room)


class SurgeNarrationTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.threshold = AudereThresholdFactory(surge_manifestation_text="{name} blazes.")

    def test_no_gm_emits_tier_line(self):
        sheet, _scene = _placed_sheet()
        _announce_surge(sheet.character, self.threshold)
        name = sheet.primary_persona.name
        self.assertTrue(
            Interaction.objects.filter(
                content=f"{name} blazes.", mode=InteractionMode.EMIT
            ).exists()
        )

    def test_prepared_surge_line_wins(self):
        sheet, _scene = _placed_sheet()
        CharacterSurgeTextFactory(character_sheet=sheet, surge_text="{name} burns gold.")
        _announce_surge(sheet.character, self.threshold)
        self.assertTrue(
            Interaction.objects.filter(content=f"{sheet.primary_persona.name} burns gold.").exists()
        )

    def test_gm_present_prompts_instead(self):
        sheet, scene = _placed_sheet()
        gm = AccountFactory()
        SceneGMParticipationFactory(scene=scene, account=gm)
        _announce_surge(sheet.character, self.threshold)
        prompt = GMPrompt.objects.get(kind=GMPromptKind.AUDERE_SURGE, addressed_to=gm)
        self.assertEqual(prompt.room_text, f"{sheet.primary_persona.name} blazes.")
        self.assertFalse(Interaction.objects.filter(content=prompt.room_text).exists())

    def test_blank_line_no_gm_stays_silent(self):
        blank = AudereThresholdFactory.build(surge_manifestation_text="")
        sheet, _scene = _placed_sheet()
        before = Interaction.objects.count()
        _announce_surge(sheet.character, blank)
        self.assertEqual(Interaction.objects.count(), before)
