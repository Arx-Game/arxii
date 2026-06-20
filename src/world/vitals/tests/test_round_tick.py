"""Tests for _apply_round_tick_damage thread-DR reduction (#1251)."""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.types import RoundTickResult
from world.magic.factories import ResonanceFactory, ThreadFactory
from world.magic.services import (
    apply_damage_reduction_from_threads,
    seed_thread_survivability_tuning,
)
from world.vitals.factories import CharacterVitalsFactory
from world.vitals.services import _apply_round_tick_damage


class RoundTickDamageThreadReductionTests(TestCase):
    """Thread-derived DR reduces DoT tick damage via _apply_round_tick_damage (#1251)."""

    def _character_with_threads(self):
        """Return an ObjectDB character whose sheet has three level-10 threads seeded."""
        sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=sheet, health=100, max_health=100)
        for _i in range(3):
            ThreadFactory(owner=sheet, resonance=ResonanceFactory(), level=10)
        return sheet.character

    def test_dot_tick_reduced_by_threads(self) -> None:
        """A thread-invested character's DoT tick debits the thread-reduced amount."""
        seed_thread_survivability_tuning()
        target = self._character_with_threads()
        before = target.sheet_data.vitals.health
        result = RoundTickResult(damage_dealt=[(None, 10)])
        _apply_round_tick_damage(target, result)
        target.sheet_data.vitals.refresh_from_db()
        dr = apply_damage_reduction_from_threads(target, 10)
        self.assertEqual(target.sheet_data.vitals.health, before - dr)
        self.assertLess(dr, 10)

    def test_dot_tick_unchanged_without_threads(self) -> None:
        """A character without threads takes the full authored DoT damage (baseline 0)."""
        seed_thread_survivability_tuning()
        sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=sheet, health=100, max_health=100)
        target = sheet.character
        before = target.sheet_data.vitals.health
        result = RoundTickResult(damage_dealt=[(None, 10)])
        _apply_round_tick_damage(target, result)
        target.sheet_data.vitals.refresh_from_db()
        self.assertEqual(target.sheet_data.vitals.health, before - 10)

    def test_zero_amount_skipped(self) -> None:
        """A zero-amount entry in damage_dealt is skipped without touching health."""
        seed_thread_survivability_tuning()
        sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=sheet, health=100, max_health=100)
        target = sheet.character
        before = target.sheet_data.vitals.health
        result = RoundTickResult(damage_dealt=[(None, 0)])
        _apply_round_tick_damage(target, result)
        target.sheet_data.vitals.refresh_from_db()
        self.assertEqual(target.sheet_data.vitals.health, before)
