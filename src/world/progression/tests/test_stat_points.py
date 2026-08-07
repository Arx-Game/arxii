"""Level Stat Points (#3001): one spendable point per class level past the first.

The points live in the levels themselves: a spend is active iff its
level_granted <= the character's current level, so a level reversal reduces
to one comparison (mirrors Maturation Points, #2756).
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassFactory
from world.classes.models import PathStage
from world.classes.services import set_primary_class_level
from world.progression.exceptions import (
    StatPointCapReachedError,
    StatPointNoPointsError,
    StatPointNotAStatError,
)
from world.progression.models import LevelStatPointSpend, MaturationStatCap
from world.progression.services.stat_points import (
    available_stat_points,
    spend_level_stat_point,
    stat_points_earned,
    sync_level_stat_point_spends,
)
from world.traits.constants import STAT_DISPLAY_DIVISOR
from world.traits.factories import TraitFactory
from world.traits.models import CharacterTraitValue, TraitCategory, TraitType


class StatPointArithmeticTests(TestCase):
    def test_one_point_per_level_past_the_first(self):
        cases = [(0, 0), (1, 0), (2, 1), (5, 4), (21, 20)]
        for level, expected in cases:
            with self.subTest(level=level):
                self.assertEqual(stat_points_earned(level), expected)


class StatPointServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.character_class = CharacterClassFactory()
        cls.stat = TraitFactory(
            name="stamina_stat_point_test",
            trait_type=TraitType.STAT,
            category=TraitCategory.PHYSICAL,
        )
        cls.skill = TraitFactory(name="skill_stat_point_test", trait_type=TraitType.SKILL)
        MaturationStatCap.objects.create(path_stage=PathStage.PROSPECT, stat_cap=5)
        MaturationStatCap.objects.create(path_stage=PathStage.POTENTIAL, stat_cap=6)

    def _sheet(self, level=3):
        sheet = CharacterSheetFactory()
        set_primary_class_level(sheet.character, self.character_class, level)
        return sheet

    def test_available_points_derive_from_level(self):
        sheet = self._sheet(level=4)
        self.assertEqual(available_stat_points(sheet), 3)
        spend_level_stat_point(sheet, self.stat)
        self.assertEqual(available_stat_points(sheet), 2)

    def test_level_one_has_no_points(self):
        sheet = self._sheet(level=1)
        self.assertEqual(available_stat_points(sheet), 0)
        with self.assertRaises(StatPointNoPointsError):
            spend_level_stat_point(sheet, self.stat)

    def test_spend_raises_stat_by_one_display_dot(self):
        sheet = self._sheet(level=3)
        spend_level_stat_point(sheet, self.stat)
        value = CharacterTraitValue.objects.get(character=sheet, trait=self.stat).value
        self.assertEqual(value, STAT_DISPLAY_DIVISOR)
        spend = LevelStatPointSpend.objects.get()
        self.assertEqual(spend.level_granted, 2)

    def test_non_stat_trait_rejected(self):
        sheet = self._sheet(level=3)
        with self.assertRaises(StatPointNotAStatError):
            spend_level_stat_point(sheet, self.skill)

    def test_cap_binds_in_display_dots(self):
        sheet = self._sheet(level=2)  # PROSPECT: cap 5
        CharacterTraitValue.objects.create(
            character=sheet, trait=self.stat, value=5 * STAT_DISPLAY_DIVISOR
        )
        with self.assertRaises(StatPointCapReachedError):
            spend_level_stat_point(sheet, self.stat)

    def test_level_reversal_deactivates_and_refunds(self):
        sheet = self._sheet(level=3)
        spend_level_stat_point(sheet, self.stat)  # level 2's point
        spend_level_stat_point(sheet, self.stat)  # level 3's point
        value = CharacterTraitValue.objects.get(character=sheet, trait=self.stat).value
        self.assertEqual(value, 2 * STAT_DISPLAY_DIVISOR)

        set_primary_class_level(sheet.character, self.character_class, 2)
        flipped = sync_level_stat_point_spends(sheet)

        self.assertEqual(flipped, 1)
        value = CharacterTraitValue.objects.get(character=sheet, trait=self.stat).value
        self.assertEqual(value, STAT_DISPLAY_DIVISOR)
        self.assertEqual(available_stat_points(sheet), 0)

        # Re-leveling reactivates the dormant spend rather than granting anew.
        set_primary_class_level(sheet.character, self.character_class, 3)
        flipped = sync_level_stat_point_spends(sheet)
        self.assertEqual(flipped, 1)
        value = CharacterTraitValue.objects.get(character=sheet, trait=self.stat).value
        self.assertEqual(value, 2 * STAT_DISPLAY_DIVISOR)
