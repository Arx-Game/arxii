"""Tests for level-derived anima maximum (#3001).

maximum = level_zero_maximum (10) at level < 1, else maximum_per_level (100) x
level. Growth never fills the pool; shrink clamps current (clamp-not-injure).
"""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassFactory
from world.classes.services import set_primary_class_level
from world.magic.factories import CharacterAnimaFactory
from world.magic.services.anima import recompute_max_anima
from world.progression.services.advancement import apply_class_level_advance


class RecomputeMaxAnimaTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.character_class = CharacterClassFactory()

    def test_level_zero_sheet_keeps_small_pool(self) -> None:
        sheet = CharacterSheetFactory()
        anima = CharacterAnimaFactory(character=sheet, current=10, maximum=10)

        result = recompute_max_anima(sheet)

        anima.refresh_from_db()
        self.assertEqual(result, 10)
        self.assertEqual(anima.maximum, 10)
        self.assertEqual(anima.current, 10)

    def test_level_one_pool_is_one_hundred_and_growth_does_not_fill(self) -> None:
        sheet = CharacterSheetFactory()
        anima = CharacterAnimaFactory(character=sheet, current=10, maximum=10)
        set_primary_class_level(sheet.character, self.character_class, 1)

        anima.refresh_from_db()
        self.assertEqual(anima.maximum, 100)
        self.assertEqual(anima.current, 10)

    def test_level_advance_spine_scales_maximum(self) -> None:
        sheet = CharacterSheetFactory()
        anima = CharacterAnimaFactory(character=sheet, current=10, maximum=10)
        set_primary_class_level(sheet.character, self.character_class, 1)

        apply_class_level_advance(sheet, level_after=3)

        anima.refresh_from_db()
        self.assertEqual(anima.maximum, 300)
        self.assertEqual(anima.current, 10)

    def test_shrink_clamps_current_without_injury(self) -> None:
        sheet = CharacterSheetFactory()
        anima = CharacterAnimaFactory(character=sheet, current=10, maximum=10)
        set_primary_class_level(sheet.character, self.character_class, 5)
        anima.refresh_from_db()
        anima.current = 450
        anima.save(update_fields=["current"])

        set_primary_class_level(sheet.character, self.character_class, 2)

        anima.refresh_from_db()
        self.assertEqual(anima.maximum, 200)
        self.assertEqual(anima.current, 200)

    def test_no_anima_row_is_a_noop(self) -> None:
        sheet = CharacterSheetFactory()
        self.assertEqual(recompute_max_anima(sheet), 0)
