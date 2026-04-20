"""Tests for Resonance Pivot Spec A Phase 11 earn/spend services."""

from __future__ import annotations

from django.test import TestCase

from world.magic.exceptions import InvalidImbueAmount
from world.magic.factories import CharacterSheetFactory, ResonanceFactory
from world.magic.services import grant_resonance

# =============================================================================
# 11.1 — grant_resonance
# =============================================================================


class GrantResonanceTests(TestCase):
    def test_first_call_creates_row(self) -> None:
        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        cr = grant_resonance(sheet, res, 5, source="test")
        self.assertEqual(cr.balance, 5)
        self.assertEqual(cr.lifetime_earned, 5)

    def test_second_call_increments_both_fields(self) -> None:
        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        grant_resonance(sheet, res, 5, source="test")
        cr = grant_resonance(sheet, res, 7, source="test")
        self.assertEqual(cr.balance, 12)
        self.assertEqual(cr.lifetime_earned, 12)

    def test_zero_amount_rejected(self) -> None:
        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        with self.assertRaises(InvalidImbueAmount):
            grant_resonance(sheet, res, 0, source="test")
