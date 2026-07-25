"""Tests for CharacterThreadHandler.context_free_power (#2708)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassLevelFactory
from world.magic.handlers import CharacterThreadHandler
from world.magic.models import LevelPowerConfig


class ContextFreePowerTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()

    def test_zero_without_any_power_config(self) -> None:
        handler = CharacterThreadHandler(self.sheet.character)
        self.assertEqual(handler.context_free_power, 0)

    def test_includes_character_level_term(self) -> None:
        LevelPowerConfig.objects.create(pk=1, character_level_bonus=2, technique_level_bonus=0)
        CharacterClassLevelFactory(character=self.sheet, level=4)
        handler = CharacterThreadHandler(self.sheet.character)
        self.assertEqual(handler.context_free_power, 8)

    def test_is_memoized(self) -> None:
        handler = CharacterThreadHandler(self.sheet.character)
        _ = handler.context_free_power  # warm the cache
        with self.assertNumQueries(0):
            self.assertEqual(handler.context_free_power, handler.context_free_power)

    def test_invalidate_clears_it(self) -> None:
        handler = CharacterThreadHandler(self.sheet.character)
        _ = handler.context_free_power  # warm the cache
        handler.invalidate()
        self.assertNotIn("context_free_power", handler.__dict__)
