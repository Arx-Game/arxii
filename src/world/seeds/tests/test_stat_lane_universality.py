"""The seeded stat lane obeys #4551 section 5.5's universality rule (#4726, #5093).

A stat buff of a size and level, read through the seeded STAT point conversion, moves a
check by the same points the to-hit lane (check points added to a roll) gives that size
and level. The simulator's universality guard is not built yet; until it is, this checks the
one relation against the seeded rows. Values are derived (size fraction x level width), so
the two lanes agree because their seeded baselines and fractions do.
"""

from __future__ import annotations

from django.test import TestCase

from world.checks.constants import ModifierLane, ModifierSize
from world.checks.modifier_values import load_value_table
from world.seeds.checks import seed_check_resolution_tables
from world.seeds.modifier_values import seed_modifier_value_tables
from world.traits.models import PointConversionRange, TraitType

# A strength of 20: a typical stat a buff lands on.
BASE_STAT = 20


class StatLaneUniversalityTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        seed_check_resolution_tables()
        seed_modifier_value_tables()

    def test_a_stat_buff_moves_a_check_by_the_to_hit_lanes_value(self) -> None:
        to_hit = load_value_table(ModifierLane.TO_HIT)
        stat = load_value_table(ModifierLane.STAT)
        base_points = PointConversionRange.calculate_points(TraitType.STAT, BASE_STAT)
        for level in range(1, 31):
            for size in ModifierSize.values:
                units = stat.value(level, size)
                moved = (
                    PointConversionRange.calculate_points(TraitType.STAT, BASE_STAT + units)
                    - base_points
                )
                with self.subTest(level=level, size=size):
                    self.assertEqual(moved, to_hit.value(level, size))
