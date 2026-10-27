"""The seeded stat lane obeys #4551 section 5.5's universality rule (#4726).

A stat buff of a size and level, read through the seeded STAT point conversion, moves a
check by about the check lane's value for that size and level. The simulator's
universality guard is not built yet; until it is, this checks the one relation against
the seeded rows.
"""

from __future__ import annotations

from django.test import TestCase

from world.checks.constants import ModifierLane
from world.checks.modifier_models import ModifierValue
from world.seeds.checks import seed_check_resolution_tables
from world.seeds.modifier_values import seed_modifier_value_tables
from world.traits.models import PointConversionRange, TraitType

# A shown strength of 2 (stats are stored x10): a typical stat a buff lands on.
BASE_STAT = 20


class StatLaneUniversalityTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        seed_check_resolution_tables()
        seed_modifier_value_tables()

    def test_a_stat_buff_moves_a_check_by_the_check_lanes_value(self) -> None:
        check_values = {
            (row.level, row.size): row.value
            for row in ModifierValue.objects.filter(lane=ModifierLane.CHECK)
        }
        stat_rows = list(ModifierValue.objects.filter(lane=ModifierLane.STAT))
        self.assertEqual(len(stat_rows), len(check_values))
        base_points = PointConversionRange.calculate_points(TraitType.STAT, BASE_STAT)
        for row in stat_rows:
            moved = (
                PointConversionRange.calculate_points(TraitType.STAT, BASE_STAT + row.value)
                - base_points
            )
            with self.subTest(level=row.level, size=row.size):
                self.assertEqual(moved, check_values[(row.level, row.size)])
