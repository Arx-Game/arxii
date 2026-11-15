"""The pool and cap lanes seed the numbers their old coefficients gave (#5093).

Each moved rule was a coefficient times a level in code; the seeded lane rows and the data
migration that carries a staff-edited coefficient into rows must both reproduce those numbers.
The expected values are the old rules' outputs at levels 1, 11 and 26, written here as plain
numbers.
"""

from __future__ import annotations

from importlib import import_module
from pkgutil import iter_modules
from types import SimpleNamespace

from django.test import TestCase

from world.checks.constants import ModifierLane
from world.checks.modifier_models import ModifierLevelBaseline
from world.checks.modifier_values import level_baseline
from world.fatigue.models import FatigueConfig
from world.seeds.modifier_values import seed_pool_and_cap_lanes

# lane -> (level 1, level 11, level 26) under the old coefficient x level rule
_OLD_RULE_VALUES = {
    ModifierLane.ANIMA_POOL: (100, 1100, 2600),
    ModifierLane.SOUL_TETHER_SCENE_CAP: (2, 22, 52),
    ModifierLane.HOLLOW_MAX: (10, 110, 260),
    ModifierLane.OUTFIT_TRICKLE: (1, 11, 26),
    ModifierLane.TECHNIQUES_PER_GIFT: (3, 33, 78),
}


class PoolCapLaneSeedTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        seed_pool_and_cap_lanes()

    def test_each_lane_reproduces_its_old_rule_at_levels_1_11_and_26(self) -> None:
        for lane, expected in _OLD_RULE_VALUES.items():
            actual = tuple(level_baseline(level, lane) for level in (1, 11, 26))
            self.assertEqual(actual, expected, lane)

    def test_the_fatigue_level_bonus_lane_has_no_rows(self) -> None:
        self.assertFalse(
            ModifierLevelBaseline.objects.filter(lane=ModifierLane.FATIGUE_LEVEL_BONUS).exists()
        )

    def test_every_lane_has_one_row_per_level_1_to_30(self) -> None:
        for lane in _OLD_RULE_VALUES:
            levels = list(
                ModifierLevelBaseline.objects.filter(lane=lane)
                .order_by("level")
                .values_list("level", flat=True)
            )
            self.assertEqual(levels, list(range(1, 31)), lane)

    def test_a_reseed_keeps_a_staff_retune(self) -> None:
        row = ModifierLevelBaseline.objects.get(lane=ModifierLane.ANIMA_POOL, level=5)
        row.baseline = 123
        row.save()
        seed_pool_and_cap_lanes()
        self.assertEqual(level_baseline(5, ModifierLane.ANIMA_POOL), 123)

    def test_the_fatigue_config_row_is_the_shipped_terms(self) -> None:
        config = FatigueConfig.objects.get(pk=1)
        self.assertEqual(
            (config.stat_multiplier, config.willpower_multiplier, config.well_rested_percent),
            (10, 3, 150),
        )


class _Config(SimpleNamespace):
    """A config row as the migration reads it: ``objects.order_by("pk").first()``."""

    @property
    def objects(self) -> _Config:
        return self

    def order_by(self, _field: str) -> _Config:
        return self

    def first(self) -> object:
        return self.row


class _Apps:
    """Stands in for the migration's ``apps``: real baseline rows, fake config models."""

    def __init__(self, configs: dict[str, object]) -> None:
        self.configs = configs

    def get_model(self, _app: str, name: str) -> object:
        if name == "ModifierLevelBaseline":
            return ModifierLevelBaseline
        return _Config(row=self.configs.get(name))


class PoolCapLaneMigrationTests(TestCase):
    """The lane-rows data migration carries each coefficient into its lane's rows."""

    def _run(self, configs: dict[str, object]) -> None:
        # Found by its name's tail, so a renumbered chain does not break the test.
        import world.migrations as migrations_package

        name = next(
            info.name
            for info in iter_modules(migrations_package.__path__)
            if info.name.endswith("_pools_and_caps_lane_rows")
        )
        import_module(f"world.migrations.{name}").write_lane_rows(_Apps(configs), None)

    def test_defaults_when_no_config_row_exists(self) -> None:
        self._run({})
        for lane, expected in _OLD_RULE_VALUES.items():
            actual = tuple(level_baseline(level, lane) for level in (1, 11, 26))
            self.assertEqual(actual, expected, lane)

    def test_an_edited_coefficient_is_carried_into_the_rows(self) -> None:
        self._run(
            {
                "AnimaConfig": SimpleNamespace(maximum_per_level=150),
                "SoulTetherConfig": SimpleNamespace(
                    per_scene_cap_level_mult=3, hollow_max_level_mult=7
                ),
                "GiftAcquisitionConfig": SimpleNamespace(techniques_per_thread_level=4),
            }
        )
        self.assertEqual(level_baseline(11, ModifierLane.ANIMA_POOL), 1650)
        self.assertEqual(level_baseline(11, ModifierLane.SOUL_TETHER_SCENE_CAP), 33)
        self.assertEqual(level_baseline(11, ModifierLane.HOLLOW_MAX), 77)
        self.assertEqual(level_baseline(11, ModifierLane.TECHNIQUES_PER_GIFT), 44)
        self.assertEqual(level_baseline(11, ModifierLane.OUTFIT_TRICKLE), 11)

    def test_a_staff_authored_row_is_kept(self) -> None:
        ModifierLevelBaseline.objects.create(lane=ModifierLane.ANIMA_POOL, level=2, baseline=9)
        self._run({})
        self.assertEqual(level_baseline(2, ModifierLane.ANIMA_POOL), 9)
        self.assertEqual(level_baseline(3, ModifierLane.ANIMA_POOL), 300)
