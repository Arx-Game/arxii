"""Authored difficulty as a level (#5093): the helpers and the point-to-level conversion.

A standalone difficulty is a level and reads as that level's baseline; an increment is tenths
of one level's width. The data migrations convert the old point values with a rule embedded in
the migration (the old nine-rank ladder, then the nearest new baseline), tested here through
the first batch's migration module.
"""

from decimal import Decimal
from importlib import import_module

from django.test import TestCase

from world.checks.services import (
    difficulty_level_for_points,
    difficulty_points,
    difficulty_step_points,
)
from world.traits.factories import ensure_level_ladder

CONVERT = "world.migrations.0417_difficulty_levels_batch1_convert"


class DifficultyHelperTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        ensure_level_ladder()

    def test_a_level_reads_as_its_baseline(self) -> None:
        self.assertEqual(difficulty_points(1), 18)
        self.assertEqual(difficulty_points(8), 18 + 8 * 7)

    def test_level_zero_is_no_difficulty(self) -> None:
        # Review focus 4: an authored 0 still asks nothing of the roller.
        self.assertEqual(difficulty_points(0), 0)
        self.assertEqual(difficulty_step_points(0, 0), 0)
        self.assertEqual(difficulty_level_for_points(0), 0)

    def test_a_level_above_the_top_baseline_reads_the_top_baseline(self) -> None:
        self.assertEqual(difficulty_points(30), 250)
        self.assertEqual(difficulty_points(45), 250)

    def test_a_step_is_tenths_of_the_levels_width(self) -> None:
        self.assertEqual(difficulty_step_points(10, 5), 8)
        self.assertEqual(difficulty_step_points(5, 5), 4)
        self.assertEqual(difficulty_step_points(3, 5), 2)  # 2.4 rounds to 2
        self.assertEqual(difficulty_step_points(Decimal("1.500"), 5), 1)  # 1.2 rounds to 1

    def test_a_negative_step_keeps_its_sign(self) -> None:
        self.assertEqual(difficulty_step_points(-10, 5), -8)

    def test_a_step_on_a_no_difficulty_base_uses_level_ones_width(self) -> None:
        self.assertEqual(difficulty_step_points(10, 0), 8)

    def test_a_step_above_the_top_level_reuses_the_top_width(self) -> None:
        self.assertEqual(difficulty_step_points(10, 45), 8)

    def test_points_land_on_the_nearest_level_ties_to_the_lower(self) -> None:
        self.assertEqual(difficulty_level_for_points(5), 0)
        self.assertEqual(difficulty_level_for_points(9), 0)  # 9 from level 0 and from level 1
        self.assertEqual(difficulty_level_for_points(10), 1)
        self.assertEqual(difficulty_level_for_points(15), 1)
        self.assertEqual(difficulty_level_for_points(45), 4)  # level 4 is 42, level 5 is 50
        self.assertEqual(difficulty_level_for_points(46), 4)  # 4 from each: the lower level
        self.assertEqual(difficulty_level_for_points(47), 5)
        self.assertEqual(difficulty_level_for_points(50), 5)
        self.assertEqual(difficulty_level_for_points(10_000), 30)


class NoLadderTests(TestCase):
    def test_a_database_with_no_baselines_reads_zero(self) -> None:
        self.assertEqual(difficulty_points(5), 0)
        self.assertEqual(difficulty_step_points(10, 5), 0)
        self.assertEqual(difficulty_level_for_points(50), 0)


class PointConversionTests(TestCase):
    """The migration's rule, from the spec: the old rank's threshold, the nearest new baseline."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.migration = import_module(CONVERT)

    def test_each_old_rank_band_converts_to_one_level(self) -> None:
        # Old ranks start at 0 / 10 / 25 / 50 / 80 / 115 / 155 / 200 / 250; the new baselines
        # are 18 + 8 x (level - 1), so 50 sits exactly on level 5 and 250 on level 30.
        expected = {
            0: 0,
            9: 0,
            10: 1,
            24: 1,
            25: 2,
            49: 2,
            50: 5,
            79: 5,
            80: 9,
            114: 9,
            115: 13,
            154: 13,
            155: 18,
            199: 18,
            200: 24,
            249: 24,
            250: 30,
        }
        for points, level in expected.items():
            self.assertEqual(self.migration.points_to_level(points), level, f"{points} points")

    def test_a_difficulty_of_zero_stays_level_zero(self) -> None:
        # Review focus 4.
        self.assertEqual(self.migration.points_to_level(0), 0)
        self.assertEqual(self.migration.points_to_tenths(0), 0)

    def test_a_difficulty_above_the_top_old_rank_is_the_top_level(self) -> None:
        self.assertEqual(self.migration.points_to_level(10_000), 30)

    def test_a_negative_authored_value_reads_as_no_difficulty(self) -> None:
        self.assertEqual(self.migration.points_to_level(-5), 0)

    def test_an_increment_is_two_tenths_per_point(self) -> None:
        # The old ladder spent 5 points a level, so one point is two tenths of a level.
        self.assertEqual(self.migration.points_to_tenths(5), 10)
        self.assertEqual(self.migration.points_to_tenths(-5), -10)
        self.assertEqual(self.migration.points_to_tenths(Decimal("0.500")), Decimal("1.000"))

    def test_the_reverse_maps_a_level_to_the_threshold_of_its_rank(self) -> None:
        for level, points in {0: 0, 1: 10, 2: 25, 5: 50, 9: 80, 13: 115, 30: 250}.items():
            self.assertEqual(self.migration.level_to_points(level), points, f"level {level}")
        # A level no old rank converts to reverses to the rank just below it.
        self.assertEqual(self.migration.level_to_points(8), 50)

    def test_tenths_reverse_to_points(self) -> None:
        self.assertEqual(self.migration.tenths_to_points(10), 5)
        self.assertEqual(self.migration.tenths_to_points(Decimal("1.000")), Decimal("0.500"))
