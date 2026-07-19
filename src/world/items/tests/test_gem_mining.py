"""Tests for the gem mining haul engine (Build 0b slice 4)."""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from world.items.factories import (
    GemDetailsFactory,
    GemGradeFactory,
    ItemTemplateFactory,
)
from world.items.gems.constants import COMMON_VALUE_PER_QUALITY, GemAxis
from world.items.gems.mining import _grade_index, roll_gem_haul


class GradeIndexTests(TestCase):
    def test_floor_respected(self):
        self.assertGreaterEqual(_grade_index(1, 4, floor_index=1), 1)

    def test_caps_at_top(self):
        self.assertEqual(_grade_index(100, 4, floor_index=0), 3)

    def test_top_heavy_high_rolls_reach_higher_grades(self):
        self.assertLess(_grade_index(50, 5, floor_index=0), _grade_index(95, 5, floor_index=0))

    def test_single_grade_axis(self):
        self.assertEqual(_grade_index(77, 1, floor_index=0), 0)


def _roll(*values):
    """A deterministic d100 source returning ``values`` in order."""
    it = iter(values)
    return lambda: next(it)


class RollGemHaulTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        for i in range(1, 5):
            GemGradeFactory(axis=GemAxis.SIZE, sort_order=i, label=f"s{i}", multiplier=Decimal(i))
            GemGradeFactory(axis=GemAxis.PURITY, sort_order=i, label=f"p{i}", multiplier=Decimal(i))
        cls.uncut = GemGradeFactory(
            axis=GemAxis.CUT, sort_order=1, label="uncut", multiplier=Decimal("1.0")
        )
        GemGradeFactory(axis=GemAxis.CUT, sort_order=2, label="fine", multiplier=Decimal("1.5"))
        for lvl in (1, 3, 6):
            tmpl = ItemTemplateFactory(name=f"gem-{lvl}", value=100)
            GemDetailsFactory(item_template=tmpl, quality_level=lvl)

    def test_no_rare_find_yields_common_value_only(self):
        # mine_quality 3 → chance 1+3=4; occurrence roll 99 > 4 → no find.
        haul = roll_gem_haul(mine_quality=3, roll=_roll(99))
        self.assertEqual(haul.rare_finds, [])
        self.assertEqual(haul.common_value, 3 * COMMON_VALUE_PER_QUALITY)

    def test_rare_find_is_minted_uncut_with_floored_axes(self):
        # mine_quality 10 → chance 11; occurrence 5 → find; count roll 1 → one find;
        # per-find rolls type/size/purity = 10 each (boosted +10 → 20).
        haul = roll_gem_haul(mine_quality=10, roll=_roll(5, 1, 10, 10, 10))
        self.assertEqual(len(haul.rare_finds), 1)
        gem = haul.rare_finds[0].gem_or_none
        self.assertIsNotNone(gem)
        self.assertEqual(gem.cut_grade, self.uncut)  # born uncut
        self.assertGreaterEqual(gem.size_grade.sort_order, 2)  # floored above the bottom band
        self.assertGreaterEqual(gem.purity_grade.sort_order, 2)
        # loose — no holder; the caller (cron) places it
        self.assertIsNone(haul.rare_finds[0].holder_character_sheet_id)

    def test_count_is_bounded_one_to_four(self):
        # count roll 100 → 1 + (100-1) % 4 = 4 finds. Need 1(occ)+1(count)+4*3 rolls.
        rolls = [5, 100, *([10] * 12)]
        haul = roll_gem_haul(mine_quality=10, roll=_roll(*rolls))
        self.assertEqual(len(haul.rare_finds), 4)

    def test_type_is_not_floored(self):
        # A low type roll can still yield the cheapest gem type (level 1).
        haul = roll_gem_haul(mine_quality=0, minister_bonus=20, roll=_roll(1, 1, 1, 1, 1))
        gem = haul.rare_finds[0].gem_or_none
        self.assertEqual(gem.item_instance.template.gem_details.quality_level, 1)

    def test_minister_bonus_raises_chance(self):
        # mine_quality 0 alone → chance 1 (a 5 would miss); minister +20 → chance 21, 5 hits.
        haul = roll_gem_haul(mine_quality=0, minister_bonus=20, roll=_roll(5, 1, 50, 50, 50))
        self.assertEqual(len(haul.rare_finds), 1)
