"""Tests for the achievement counter helper (Phase 3)."""

from __future__ import annotations

from django.test import TestCase

from world.achievements.models import StatDefinition
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.achievement_counters import (
    STAT_KEY_DAMAGE_DEALT,
    STAT_KEY_KILLSHOTS,
    increment_combat_counter,
)


class IncrementCombatCounterTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.sheet = CharacterSheetFactory()

    def test_first_increment_creates_stat_definition(self) -> None:
        """First call creates the StatDefinition row lazily."""
        self.assertFalse(StatDefinition.objects.filter(key=STAT_KEY_DAMAGE_DEALT).exists())
        increment_combat_counter(self.sheet, STAT_KEY_DAMAGE_DEALT, 7)
        stat_def = StatDefinition.objects.get(key=STAT_KEY_DAMAGE_DEALT)
        self.assertEqual(stat_def.name, "Damage Dealt")

    def test_increment_accumulates(self) -> None:
        """Repeated increments accumulate atomically."""
        increment_combat_counter(self.sheet, STAT_KEY_DAMAGE_DEALT, 3)
        increment_combat_counter(self.sheet, STAT_KEY_DAMAGE_DEALT, 5)
        stat_def = StatDefinition.objects.get(key=STAT_KEY_DAMAGE_DEALT)
        self.assertEqual(self.sheet.stats.get(stat_def), 8)

    def test_increment_returns_new_value(self) -> None:
        result = increment_combat_counter(self.sheet, STAT_KEY_KILLSHOTS, 1)
        self.assertEqual(result, 1)
        result = increment_combat_counter(self.sheet, STAT_KEY_KILLSHOTS, 2)
        self.assertEqual(result, 3)

    def test_zero_amount_is_noop(self) -> None:
        """Increment by 0 returns current value without writing."""
        increment_combat_counter(self.sheet, STAT_KEY_DAMAGE_DEALT, 5)
        result = increment_combat_counter(self.sheet, STAT_KEY_DAMAGE_DEALT, 0)
        self.assertEqual(result, 5)

    def test_negative_amount_is_noop(self) -> None:
        """Increment by negative is treated as no-op (defensive)."""
        increment_combat_counter(self.sheet, STAT_KEY_DAMAGE_DEALT, 5)
        result = increment_combat_counter(self.sheet, STAT_KEY_DAMAGE_DEALT, -3)
        self.assertEqual(result, 5)
