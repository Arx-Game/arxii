"""The one geometric development cost curve, pinned against hand-computed numbers (#5093).

With the shipped defaults (start level 1, base cost 100, growth 150 percent) a band costs
100, 150, 225, 337.5 (338, half to even), 506.25 (506) and 759.375 (759) from character
level 1 up, and each of a band's ten steps costs a tenth of that: 10, 15, 22, 33, 50, 75.
"""

from __future__ import annotations

from django.test import TestCase

from world.magic.constants import TargetKind
from world.magic.factories import ThreadPullCostFactory
from world.magic.services.threads import get_imbue_cost_multiplier
from world.progression.models import DevelopmentCostConfig
from world.progression.services.dev_cost import (
    cumulative_dp_for_level,
    dp_cost_for_band,
    dp_cost_for_step,
)


class DevCostDefaultsTests(TestCase):
    def setUp(self) -> None:
        DevelopmentCostConfig.flush_instance_cache()

    def test_singleton_is_created_from_the_shipped_defaults(self) -> None:
        config = DevelopmentCostConfig.get_singleton()
        self.assertEqual(
            (config.start_level, config.base_cost, config.growth_percent), (1, 100, 150)
        )

    def test_band_cost_grows_once_per_level(self) -> None:
        costs = {band: dp_cost_for_band(band) for band in range(1, 7)}
        self.assertEqual(costs, {1: 100, 2: 150, 3: 225, 4: 338, 5: 506, 6: 759})

    def test_a_band_below_the_start_level_costs_the_base_cost(self) -> None:
        self.assertEqual(dp_cost_for_band(0), 100)

    def test_every_step_inside_a_band_costs_the_same(self) -> None:
        self.assertEqual(dp_cost_for_step(30), 22)
        self.assertEqual(dp_cost_for_step(30), dp_cost_for_step(39))

    def test_a_step_that_starts_in_the_next_band_costs_one_growth_step_more(self) -> None:
        self.assertEqual(dp_cost_for_step(40), 33)
        self.assertEqual(dp_cost_for_step(40), round(dp_cost_for_step(30) * 1.5))

    def test_step_costs_from_level_one_up(self) -> None:
        costs = [dp_cost_for_step(value) for value in (10, 19, 20, 29, 50, 60)]
        self.assertEqual(costs, [10, 10, 15, 15, 50, 75])

    def test_cumulative_cost_sums_the_steps_from_level_ten(self) -> None:
        expected = {10: 0, 11: 10, 20: 100, 25: 175, 30: 250, 40: 470, 50: 800, 60: 1300}
        self.assertEqual({v: cumulative_dp_for_level(v) for v in expected}, expected)

    def test_cumulative_cost_is_zero_at_or_below_the_creation_floor(self) -> None:
        self.assertEqual([cumulative_dp_for_level(v) for v in (0, 1, 5, 10)], [0, 0, 0, 0])

    def test_cumulative_cost_equals_the_sum_of_its_steps(self) -> None:
        for value in (11, 19, 20, 37, 64):
            self.assertEqual(
                cumulative_dp_for_level(value),
                sum(dp_cost_for_step(v) for v in range(10, value)),
            )

    def test_a_gift_thread_step_costs_twice_a_non_gift_step(self) -> None:
        ThreadPullCostFactory(tier=1, target_kind=None, imbue_cost_multiplier=1, label="soft")
        ThreadPullCostFactory(
            tier=1, target_kind=TargetKind.GIFT, imbue_cost_multiplier=2, label="gift-soft"
        )
        step = dp_cost_for_step(110)
        gift = step * get_imbue_cost_multiplier(TargetKind.GIFT)
        plain = step * get_imbue_cost_multiplier(TargetKind.TRAIT)
        self.assertEqual((plain, gift), (step, 2 * step))


class DevCostTunedTests(TestCase):
    """Staff retune the row; the curve follows it."""

    def setUp(self) -> None:
        DevelopmentCostConfig.flush_instance_cache()
        self.addCleanup(DevelopmentCostConfig.flush_instance_cache)

    def test_growth_and_base_cost_come_from_the_row(self) -> None:
        DevelopmentCostConfig.objects.update_or_create(
            pk=1, defaults={"start_level": 2, "base_cost": 200, "growth_percent": 200}
        )
        # Band 2 is the start (200); band 3 doubles (400); band 1 sits below it (200).
        self.assertEqual([dp_cost_for_band(b) for b in (1, 2, 3, 4)], [200, 200, 400, 800])
        self.assertEqual([dp_cost_for_step(v) for v in (10, 20, 30, 40)], [20, 20, 40, 80])
        self.assertEqual(cumulative_dp_for_level(30), 10 * 20 + 10 * 20)

    def test_flat_growth_makes_every_band_cost_the_same(self) -> None:
        DevelopmentCostConfig.objects.update_or_create(pk=1, defaults={"growth_percent": 100})
        self.assertEqual({dp_cost_for_step(v) for v in (10, 40, 90)}, {10})

    def test_a_step_never_costs_less_than_one_point(self) -> None:
        DevelopmentCostConfig.objects.update_or_create(pk=1, defaults={"base_cost": 5})
        self.assertEqual(dp_cost_for_step(10), 1)
