"""Tests for _apply_round_tick_damage consulting Succor cover (#1744)."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.types import RoundTickResult
from world.vitals.factories import CharacterVitalsFactory
from world.vitals.services import _apply_round_tick_damage


class ApplyRoundTickDamageSuccorTests(TestCase):
    """`_apply_round_tick_damage` multiplies DoT damage by the target's Succor cover."""

    def _character_with_health(self, health: int = 50):
        sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=sheet, health=health, max_health=100)
        return sheet.character

    def test_full_cover_prevents_health_loss(self) -> None:
        """A 0.0 multiplier (clean block) leaves health untouched."""
        target = self._character_with_health(health=50)
        result = RoundTickResult(damage_dealt=[(None, 10)])
        with patch("actions.round_context.get_active_round_context") as mock_ctx_getter:
            mock_ctx_getter.return_value.get_cover_for.return_value = 0.0
            _apply_round_tick_damage(target, result)
        target.sheet_data.vitals.refresh_from_db()
        self.assertEqual(target.sheet_data.vitals.health, 50)

    def test_partial_cover_halves_damage(self) -> None:
        """A 0.5 multiplier (partial cover) halves the tick amount before debiting health."""
        target = self._character_with_health(health=50)
        result = RoundTickResult(damage_dealt=[(None, 10)])
        with patch("actions.round_context.get_active_round_context") as mock_ctx_getter:
            mock_ctx_getter.return_value.get_cover_for.return_value = 0.5
            _apply_round_tick_damage(target, result)
        target.sheet_data.vitals.refresh_from_db()
        self.assertEqual(target.sheet_data.vitals.health, 45)

    def test_no_active_round_context_applies_full_damage(self) -> None:
        """No active round (the common case) is a no-op — full damage applies."""
        target = self._character_with_health(health=50)
        result = RoundTickResult(damage_dealt=[(None, 10)])
        with patch("actions.round_context.get_active_round_context") as mock_ctx_getter:
            mock_ctx_getter.return_value = None
            _apply_round_tick_damage(target, result)
        target.sheet_data.vitals.refresh_from_db()
        self.assertEqual(target.sheet_data.vitals.health, 40)
