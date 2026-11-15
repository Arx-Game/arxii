"""The rank ladder is built from the dense level baselines (#5093).

Baselines are 18 + 8 x (level - 1) for levels 1-30, so rank N starts at the level-N
baseline and one level's width is 8 points everywhere.
"""

from importlib import import_module
from pathlib import Path

from django.test import TestCase

from world import migrations
from world.checks.constants import ModifierLane
from world.checks.exceptions import ModifierConfigError
from world.checks.modifier_models import ModifierLevelBaseline
from world.checks.modifier_values import level_baseline, level_width, load_baselines
from world.checks.slide import band_position, load_ranks
from world.traits.models import CheckRank


class LevelLadderTests(TestCase):
    """U-keep: pure ladder construction math, with no player seam of its own."""

    @classmethod
    def setUpTestData(cls) -> None:
        for level in range(1, 31):
            ModifierLevelBaseline.objects.create(
                lane=ModifierLane.CHECK, level=level, baseline=18 + 8 * (level - 1)
            )
        for rank in range(31):
            CheckRank.objects.create(rank=rank, name=f"Rank {rank}")

    def test_level_width_is_the_step_to_the_next_level(self) -> None:
        self.assertEqual(level_width(1), 8)
        self.assertEqual(level_width(29), 8)

    def test_above_the_top_row_the_last_width_and_baseline_are_reused(self) -> None:
        # Review focus 1: an NPC at level 30 or a thread rung above 26.
        self.assertEqual(level_width(30), 8)
        self.assertEqual(level_width(45), 8)
        self.assertEqual(level_baseline(31), level_baseline(30))
        self.assertEqual(level_baseline(30), 18 + 8 * 29)

    def test_a_level_below_the_first_row_is_a_configuration_error(self) -> None:
        with self.assertRaises(ModifierConfigError):
            level_baseline(0)
        with self.assertRaises(ModifierConfigError):
            level_width(0)

    def test_an_empty_lane_is_a_configuration_error(self) -> None:
        with self.assertRaises(ModifierConfigError):
            level_baseline(3, ModifierLane.STAT)

    def test_a_lane_with_one_row_has_no_width(self) -> None:
        ModifierLevelBaseline.objects.create(lane=ModifierLane.STAT, level=1, baseline=5)
        with self.assertRaises(ModifierConfigError):
            level_width(1, ModifierLane.STAT)

    def test_baselines_load_in_one_query(self) -> None:
        with self.assertNumQueries(1):
            table = load_baselines()
        self.assertEqual(table.baseline(11), 98)
        self.assertEqual(table.width(11), 8)

    def test_the_ladder_starts_each_rank_at_its_level_baseline(self) -> None:
        ranks = {step.rank: step.min_points for step in load_ranks()}
        self.assertEqual(ranks[0], 0)
        self.assertEqual(ranks[1], 18)
        self.assertEqual(ranks[11], 98)
        self.assertEqual(ranks[30], 250)

    def test_a_total_at_a_baseline_is_that_rank(self) -> None:
        self.assertEqual(band_position(18).rank.rank, 1)
        self.assertEqual(band_position(98).rank.rank, 11)
        self.assertEqual(band_position(98).share, 0.0)

    def test_a_total_part_way_through_a_level_has_a_share(self) -> None:
        position = band_position(102)
        self.assertEqual(position.rank.rank, 11)
        self.assertEqual(position.share, 0.5)
        self.assertEqual(position.text, "Rank 11, 50% toward Rank 12")

    def test_a_total_below_rank_one_is_rank_zero_with_rank_one_next(self) -> None:
        # Review focus 2: a level-0 or brand-new character never crashes.
        position = band_position(5)
        self.assertEqual(position.rank.rank, 0)
        self.assertEqual(position.next_rank.rank, 1)
        self.assertAlmostEqual(position.share, 5 / 18)

    def test_a_total_below_the_whole_ladder_has_no_rank(self) -> None:
        position = band_position(-3)
        self.assertIsNone(position.rank)
        self.assertEqual(position.next_rank.rank, 0)

    def test_without_a_rank_zero_row_a_low_total_is_below_rank_one(self) -> None:
        CheckRank.objects.filter(rank=0).delete()
        position = band_position(5)
        self.assertIsNone(position.rank)
        self.assertEqual(position.next_rank.rank, 1)
        self.assertEqual(position.value, 0.0)

    def test_the_top_rank_has_no_next_rank(self) -> None:
        position = band_position(900)
        self.assertEqual(position.rank.rank, 30)
        self.assertIsNone(position.next_rank)

    def test_get_rank_for_points_and_difference_read_the_same_ladder(self) -> None:
        self.assertEqual(CheckRank.get_rank_for_points(105).rank, 11)
        self.assertEqual(CheckRank.get_rank_difference(105, 50), 11 - 5)

    def test_no_ranks_means_an_empty_ladder_without_reading_baselines(self) -> None:
        CheckRank.objects.all().delete()
        ModifierLevelBaseline.objects.all().delete()
        self.assertEqual(load_ranks(), [])
        self.assertIsNone(band_position(40).rank)


class CheckLadderRowsMigrationTests(TestCase):
    """U-keep: a data migration, which no journey runs.

    ``0411_check_ladder_rows`` gives a database with ranks the rows that replace thresholds."""

    @staticmethod
    def _run() -> None:
        from django.apps import apps

        # Found by suffix, so a renumbering of the migration does not break the test.
        name = next(
            path.stem for path in Path(migrations.__file__).parent.glob("*_check_ladder_rows.py")
        )
        migration = import_module(f"world.migrations.{name}")
        migration.write_ladder_rows(apps, None)

    def test_a_database_with_ranks_gets_baselines_and_the_ranks_above(self) -> None:
        for rank in range(9):
            CheckRank.objects.create(rank=rank, name=f"Old {rank}")
        ModifierLevelBaseline.objects.create(lane=ModifierLane.CHECK, level=3, baseline=99)

        self._run()

        self.assertEqual(level_baseline(1), 18)
        self.assertEqual(level_baseline(3), 99)  # a staff-authored row is kept
        self.assertEqual(level_baseline(30), 250)
        self.assertEqual(CheckRank.objects.count(), 31)
        self.assertEqual(CheckRank.objects.get(rank=2).name, "Old 2")
        self.assertEqual(CheckRank.objects.get(rank=9).name, "Rank 9")

    def test_an_empty_database_is_left_for_the_seeds(self) -> None:
        self._run()

        self.assertFalse(CheckRank.objects.exists())
        self.assertFalse(ModifierLevelBaseline.objects.exists())
