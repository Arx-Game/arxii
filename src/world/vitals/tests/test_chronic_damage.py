"""Tests for apply_clamped_chronic_damage — the non-lethal long-term damage clamp.

The long-term/chronic tier (#520 §5.3) reduces health directly with a clamp that
keeps post-damage health strictly above the knockout floor, and never heals.
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.vitals.factories import CharacterVitalsFactory
from world.vitals.services import apply_clamped_chronic_damage


class ApplyClampedChronicDamageTests(TestCase):
    def _vitals(self, health: int, max_health: int = 100):
        sheet = CharacterSheetFactory()
        return CharacterVitalsFactory(character_sheet=sheet, health=health, max_health=max_health)

    def test_reduces_health(self) -> None:
        vitals = self._vitals(health=100)
        removed = apply_clamped_chronic_damage(vitals.character_sheet, 10)
        vitals.refresh_from_db()
        self.assertEqual(vitals.health, 90)
        self.assertEqual(removed, 10)

    def test_never_below_knockout_floor(self) -> None:
        # floor = int(0.2 * 100) + 1 = 21; from 25 a 50-damage hit clamps to 21.
        vitals = self._vitals(health=25)
        removed = apply_clamped_chronic_damage(vitals.character_sheet, 50)
        vitals.refresh_from_db()
        self.assertEqual(vitals.health, 21)
        self.assertEqual(removed, 4)
        self.assertGreater(vitals.health_percentage, 0.2)

    def test_never_heals_when_already_below_floor(self) -> None:
        vitals = self._vitals(health=10)
        removed = apply_clamped_chronic_damage(vitals.character_sheet, 50)
        vitals.refresh_from_db()
        self.assertEqual(vitals.health, 10)
        self.assertEqual(removed, 0)

    def test_zero_or_negative_amount_is_noop(self) -> None:
        vitals = self._vitals(health=80)
        self.assertEqual(apply_clamped_chronic_damage(vitals.character_sheet, 0), 0)
        self.assertEqual(apply_clamped_chronic_damage(vitals.character_sheet, -5), 0)
        vitals.refresh_from_db()
        self.assertEqual(vitals.health, 80)
