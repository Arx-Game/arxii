"""A vow added effect's severity, duration and damage scale through their own lanes (#5093).

The per-rung columns used to be a plain number added for each rung (10 thread levels) above the
effect's unlock. They are now tenths of what the effect's lane baseline gains over those rungs,
and the seeded lanes gain 10 a rung, so every number below is the old rule's output, written
here as a plain number: rungs above the unlock times the column.
"""

from __future__ import annotations

from types import SimpleNamespace

from django.test import TestCase

from world.checks.constants import ModifierLane
from world.checks.modifier_models import ModifierLevelBaseline
from world.covenants.added_effects import load_vow_effect_lanes, vow_effect_bonuses
from world.seeds.modifier_values import seed_pool_and_cap_lanes


def _effect(unlock: int, severity: int = 0, duration: int = 0, damage: int = 0) -> SimpleNamespace:
    """The three columns and the unlock, which is all ``vow_effect_bonuses`` reads of a row."""
    return SimpleNamespace(
        unlock_thread_level=unlock,
        severity_tenths=severity,
        duration_tenths=duration,
        damage_tenths=damage,
    )


class VowEffectLaneTests(TestCase):
    """U-keep: per-rung lane arithmetic with no player seam of its own."""

    @classmethod
    def setUpTestData(cls) -> None:
        seed_pool_and_cap_lanes()

    def test_the_seeded_lanes_give_the_old_rungs_above_unlock_times_the_column(self) -> None:
        # (unlock thread level, vow thread level, column, bonus), the bonus being the old rule's
        # (rung - unlock rung) x column: rungs 0 -> 0, 0 -> 1, 2 -> 5, 3 -> 30, 9 -> 9, 2 -> 2.
        cases = (
            (0, 0, 3, 0),
            (0, 10, 3, 3),
            (20, 50, 2, 6),
            (30, 300, 4, 108),
            (95, 95, 7, 0),
            (25, 29, 5, 0),
        )
        for unlock, level, column, expected in cases:
            bonuses = vow_effect_bonuses(_effect(unlock, column, column, column), level)
            self.assertEqual(
                (bonuses.severity, bonuses.duration, bonuses.damage),
                (expected,) * 3,
                (unlock, level, column),
            )

    def test_a_thread_between_rungs_reads_its_whole_rung(self) -> None:
        bonuses = vow_effect_bonuses(_effect(0, severity=2), 49)
        self.assertEqual(bonuses.severity, 8)

    def test_each_column_reads_its_own_lane(self) -> None:
        row = ModifierLevelBaseline.objects.get(lane=ModifierLane.VOW_EFFECT_DAMAGE, level=5)
        row.baseline = 100  # the seed is 50: 8 more gained from rung 2 (20) to rung 5 (100)
        row.save()
        bonuses = vow_effect_bonuses(_effect(20, severity=2, duration=2, damage=2), 50)
        self.assertEqual((bonuses.severity, bonuses.duration, bonuses.damage), (6, 6, 16))

    def test_a_gain_rounds_half_up(self) -> None:
        row = ModifierLevelBaseline.objects.get(lane=ModifierLane.VOW_EFFECT_SEVERITY, level=3)
        row.baseline = 35  # 3 tenths of the 35 gained over three rungs is 10.5
        row.save()
        self.assertEqual(vow_effect_bonuses(_effect(0, severity=3), 30).severity, 11)

    def test_a_secondary_vow_scales_by_potency_after_the_lane(self) -> None:
        bonuses = vow_effect_bonuses(_effect(0, severity=10), 50, potency_tenths=5)
        self.assertEqual(bonuses.severity, 25)

    def test_the_lanes_loaded_once_serve_every_effect_without_another_query(self) -> None:
        lanes = load_vow_effect_lanes()
        with self.assertNumQueries(0):
            for column in (1, 2, 3):
                vow_effect_bonuses(_effect(0, column, column, column), 50, lanes=lanes)

    def test_an_effect_with_no_columns_or_no_rungs_above_reads_no_lane(self) -> None:
        with self.assertNumQueries(0):
            vow_effect_bonuses(_effect(0), 300)
            vow_effect_bonuses(_effect(100, severity=3), 100)
