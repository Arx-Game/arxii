"""A modifier's value is its size's fraction times one level's width (#5093).

The override rows, the vow size step, the example seeds and the data migration that turns
equal-to-seed rows into derived values.
"""

from decimal import Decimal
from importlib import import_module

from django.apps import apps as django_apps
from django.test import SimpleTestCase, TestCase

from world.checks.constants import ModifierLane, ModifierSize
from world.checks.exceptions import ModifierConfigError
from world.checks.modifier_models import ModifierLevelBaseline, ModifierSizeFraction, ModifierValue
from world.checks.modifier_values import BaselineTable, ValueTable, load_value_table
from world.seeds.modifier_values import seed_modifier_value_tables

# 18 + 8 x (level - 1) for levels 1-30: one level's width is 8 everywhere.
_CHECK_BASELINES = BaselineTable(
    levels=tuple(range(1, 31)), baselines=tuple(18 + 8 * (level - 1) for level in range(1, 31))
)
_FRACTIONS = {
    ModifierSize.MINOR: Decimal("0.125"),
    ModifierSize.MODERATE: Decimal("0.25"),
    ModifierSize.LARGE: Decimal("0.5"),
    ModifierSize.EXCEPTIONAL: Decimal("0.75"),
    ModifierSize.PARAMOUNT: Decimal(1),
}


class DerivedValueTests(SimpleTestCase):
    """U-keep: pure fraction-times-width arithmetic on an in-memory table."""

    TABLE = ValueTable(overrides={}, fractions=_FRACTIONS, baselines=_CHECK_BASELINES)

    def test_a_value_is_the_fraction_times_the_levels_width(self) -> None:
        self.assertEqual(self.TABLE.value(11, ModifierSize.LARGE), 4)
        self.assertEqual(self.TABLE.value(11, ModifierSize.MINOR), 1)
        self.assertEqual(self.TABLE.value(11, ModifierSize.PARAMOUNT), 8)

    def test_the_width_comes_from_the_baseline_rows_at_that_level(self) -> None:
        table = ValueTable(
            fractions=_FRACTIONS,
            baselines=BaselineTable(levels=(1, 2, 3), baselines=(10, 30, 40)),
        )
        # Level 1 is 20 wide, level 2 is 10 wide, and level 9 reuses the top row's 10.
        self.assertEqual(table.value(1, ModifierSize.LARGE), 10)
        self.assertEqual(table.value(2, ModifierSize.LARGE), 5)
        self.assertEqual(table.value(9, ModifierSize.LARGE), 5)

    def test_an_override_row_at_the_exact_level_wins(self) -> None:
        table = ValueTable(
            overrides={(11, ModifierSize.LARGE): 9},
            fractions=_FRACTIONS,
            baselines=_CHECK_BASELINES,
        )

        self.assertEqual(table.value(11, ModifierSize.LARGE), 9)
        # An override does not cover the levels around it.
        self.assertEqual(table.value(12, ModifierSize.LARGE), 4)

    def test_a_size_with_no_fraction_and_no_override_has_no_value(self) -> None:
        table = ValueTable(
            fractions={ModifierSize.LARGE: Decimal("0.5")}, baselines=_CHECK_BASELINES
        )

        self.assertIsNone(table.value(11, ModifierSize.MINOR))
        self.assertIsNone(table.signed_value(-3, 11, ModifierSize.MINOR))

    def test_a_debuff_keeps_its_sign(self) -> None:
        # Review focus 3.
        self.assertEqual(self.TABLE.signed_value(-3, 11, ModifierSize.LARGE), -4)
        self.assertEqual(self.TABLE.signed_value(3, 11, ModifierSize.LARGE), 4)

    def test_a_small_fraction_never_rounds_a_penalty_to_zero(self) -> None:
        table = ValueTable(
            fractions={ModifierSize.MINOR: Decimal("0.040")}, baselines=_CHECK_BASELINES
        )

        # 0.04 x 8 = 0.32 rounds to 0, but a nonzero fraction is worth at least 1.
        self.assertEqual(table.signed_value(-5, 4, ModifierSize.MINOR), -1)
        self.assertEqual(table.signed_value(5, 4, ModifierSize.MINOR), 1)

    def test_a_zero_fraction_is_worth_nothing(self) -> None:
        table = ValueTable(fractions={ModifierSize.MINOR: Decimal(0)}, baselines=_CHECK_BASELINES)

        self.assertEqual(table.value(4, ModifierSize.MINOR), 0)

    def test_a_lane_with_no_baseline_rows_is_a_configuration_error(self) -> None:
        table = ValueTable(fractions=_FRACTIONS)

        with self.assertRaises(ModifierConfigError):
            table.value(4, ModifierSize.LARGE)


class VowStepTests(SimpleTestCase):
    """U-keep: pure vow size-step arithmetic on an in-memory table, no seam a journey reaches."""

    TABLE = ValueTable(fractions=_FRACTIONS, baselines=_CHECK_BASELINES)

    def test_the_step_is_the_fraction_gap_times_the_width_and_tenths(self) -> None:
        # (0.75 - 0.5) x 8 x 10 / 10 = 2, the same as round((frac(EXC) - frac(LARGE)) x 8).
        self.assertEqual(self.TABLE.vow_step(4, 11, ModifierSize.LARGE, 10), 2)
        self.assertEqual(self.TABLE.vow_step(4, 11, ModifierSize.LARGE, 5), 1)
        # 0.25 x 8 x 3 / 10 = 0.6, rounded half up.
        self.assertEqual(self.TABLE.vow_step(4, 11, ModifierSize.LARGE, 3), 1)

    def test_a_debuffs_step_is_a_further_penalty(self) -> None:
        self.assertEqual(self.TABLE.vow_step(-4, 11, ModifierSize.LARGE, 10), -2)

    def test_the_step_is_zero_without_a_fraction_for_either_size(self) -> None:
        self.assertEqual(self.TABLE.vow_step(4, 11, ModifierSize.PARAMOUNT, 10), 0)
        table = ValueTable(
            fractions={ModifierSize.LARGE: Decimal("0.5")}, baselines=_CHECK_BASELINES
        )
        self.assertEqual(table.vow_step(4, 11, ModifierSize.LARGE, 10), 0)

    def test_an_override_row_does_not_change_the_step(self) -> None:
        table = ValueTable(
            overrides={(11, ModifierSize.LARGE): 9},
            fractions=_FRACTIONS,
            baselines=_CHECK_BASELINES,
        )

        self.assertEqual(table.vow_step(4, 11, ModifierSize.LARGE, 10), 2)


class SeededValuesTests(TestCase):
    """U-keep: the seed output is read by every journey but only compared lane by lane here.

    The example seed writes no value rows, and each lane's Large lands on its old ladder."""

    # Lane -> Large values the example ladders had at levels 1, 6, 11, 16, 21 and 26.
    OLD_LARGE = {
        ModifierLane.TO_HIT: (3, 10, 16, 23, 30, 36),
        ModifierLane.STAT: (3, 10, 16, 23, 30, 36),
        ModifierLane.DAMAGE: (2, 4, 6, 8, 10, 12),
        ModifierLane.PARTIAL_PROTECTION: (5, 8, 10, 13, 16, 20),
    }

    @classmethod
    def setUpTestData(cls) -> None:
        seed_modifier_value_tables()

    def test_no_override_rows_are_seeded(self) -> None:
        self.assertFalse(ModifierValue.objects.exists())

    def test_the_check_lanes_large_buff_is_half_a_level(self) -> None:
        table = load_value_table(ModifierLane.CHECK)

        self.assertEqual(
            [table.value(level, ModifierSize.LARGE) for level in (1, 6, 11, 16, 21, 26)],
            [4] * 6,
        )
        self.assertEqual([table.value(11, size) for size in ModifierSize.values], [1, 2, 4, 6, 8])

    def test_each_derived_lanes_large_value_is_within_one_of_its_old_example(self) -> None:
        for lane, old_values in self.OLD_LARGE.items():
            table = load_value_table(lane)
            for level, old in zip((1, 6, 11, 16, 21, 26), old_values, strict=True):
                with self.subTest(lane=lane, level=level):
                    self.assertLessEqual(abs(table.value(level, ModifierSize.LARGE) - old), 1)

    def test_every_lane_has_a_fraction_for_every_size(self) -> None:
        for lane in (ModifierLane.CHECK, *self.OLD_LARGE):
            with self.subTest(lane=lane):
                self.assertEqual(
                    ModifierSizeFraction.objects.filter(lane=lane).count(), len(ModifierSize)
                )
                self.assertEqual(ModifierLevelBaseline.objects.filter(lane=lane).count(), 30)


class DataMigrationTests(TestCase):
    """U-keep: a data migration, which no journey runs.

    0414 deletes rows equal to the old seed, keeps edited ones, and writes the fractions."""

    def setUp(self) -> None:
        self.migration = import_module("world.migrations.0414_modifier_values_become_overrides")

    def _row(self, lane: str, level: int, size: int, value: int) -> None:
        ModifierValue.objects.create(lane=lane, level=level, size=size, value=value)

    def test_equal_rows_go_and_edited_rows_stay_as_overrides(self) -> None:
        self._row(ModifierLane.CHECK, 11, ModifierSize.LARGE, 16)  # the old seed
        self._row(ModifierLane.CHECK, 11, ModifierSize.MINOR, 4)  # the old seed (16 x 0.25)
        self._row(ModifierLane.CHECK, 11, ModifierSize.MODERATE, 9)  # staff edited (seed was 8)
        self._row(ModifierLane.CHECK, 7, ModifierSize.LARGE, 13)  # a level the seed never wrote
        self._row(ModifierLane.DAMAGE, 6, ModifierSize.LARGE, 4)  # the old seed

        self.migration.derive_values_from_fractions(django_apps, None)

        kept = set(ModifierValue.objects.values_list("lane", "level", "size", "value"))
        self.assertEqual(
            kept,
            {
                (ModifierLane.CHECK, 11, ModifierSize.MODERATE, 9),
                (ModifierLane.CHECK, 7, ModifierSize.LARGE, 13),
            },
        )

    def test_a_lane_with_rows_gets_its_fractions_and_baselines_without_overwriting(self) -> None:
        self._row(ModifierLane.DAMAGE, 6, ModifierSize.LARGE, 4)
        ModifierSizeFraction.objects.create(
            lane=ModifierLane.DAMAGE, size=ModifierSize.LARGE, fraction=Decimal("0.600")
        )

        self.migration.derive_values_from_fractions(django_apps, None)

        fractions = dict(
            ModifierSizeFraction.objects.filter(lane=ModifierLane.DAMAGE).values_list(
                "size", "fraction"
            )
        )
        self.assertEqual(fractions[ModifierSize.LARGE], Decimal("0.600"))
        self.assertEqual(fractions[ModifierSize.MINOR], Decimal("0.125"))
        self.assertEqual(ModifierLevelBaseline.objects.filter(lane=ModifierLane.DAMAGE).count(), 30)
        # Large at level 6 is 0.6 x the 8-point width: the migrated lane still values it.
        self.assertEqual(load_value_table(ModifierLane.DAMAGE).value(6, ModifierSize.LARGE), 5)

    def test_a_database_with_no_value_rows_is_untouched(self) -> None:
        self.migration.derive_values_from_fractions(django_apps, None)

        self.assertFalse(ModifierSizeFraction.objects.exists())
        self.assertFalse(ModifierLevelBaseline.objects.exists())
