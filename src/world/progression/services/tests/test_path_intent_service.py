from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import PathFactory
from world.progression.models.path_intent import PathIntent
from world.progression.services.path_intent import clear_path_intent, set_path_intent


class PathIntentServiceTests(TestCase):
    def setUp(self) -> None:
        PathIntent.flush_instance_cache()
        self.sheet = CharacterSheetFactory()
        self.path = PathFactory(name="Champion")
        self.other_path = PathFactory(name="Sentinel")

    def test_set_creates_intent(self) -> None:
        intent = set_path_intent(self.sheet, self.path)
        self.assertEqual(intent.character_sheet, self.sheet)
        self.assertEqual(intent.intended_path, self.path)

    def test_set_overwrites_existing(self) -> None:
        set_path_intent(self.sheet, self.path)
        intent = set_path_intent(self.sheet, self.other_path)
        self.assertEqual(intent.intended_path, self.other_path)
        self.assertEqual(PathIntent.objects.filter(character_sheet=self.sheet).count(), 1)

    def test_clear_removes_intent(self) -> None:
        set_path_intent(self.sheet, self.path)
        clear_path_intent(self.sheet)
        self.assertFalse(PathIntent.objects.filter(character_sheet=self.sheet).exists())

    def test_clear_is_idempotent(self) -> None:
        clear_path_intent(self.sheet)  # no row; must not raise
