"""Tests for the vitals system models and constants."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.vitals.constants import (
    WOUND_DESCRIPTIONS,
    CharacterStatus,
)
from world.vitals.models import CharacterVitals


class CharacterVitalsTests(TestCase):
    """Tests for CharacterVitals model."""

    def test_create_vitals_default_status(self) -> None:
        sheet = CharacterSheetFactory()
        vitals = CharacterVitals.objects.create(character_sheet=sheet)
        self.assertEqual(vitals.status, CharacterStatus.ALIVE)
        self.assertIsNone(vitals.died_at)
        self.assertIsNone(vitals.unconscious_at)

    def test_str_includes_sheet_and_status(self) -> None:
        sheet = CharacterSheetFactory()
        vitals = CharacterVitals.objects.create(character_sheet=sheet)
        result = str(vitals)
        self.assertIn(str(sheet), result)
        self.assertIn("Alive", result)

    def test_str_with_dead_status(self) -> None:
        sheet = CharacterSheetFactory()
        vitals = CharacterVitals.objects.create(
            character_sheet=sheet,
            status=CharacterStatus.DEAD,
        )
        self.assertIn("Dead", str(vitals))


class WoundDescriptionConstantsTests(TestCase):
    """Tests for wound description threshold logic."""

    def _get_wound_description(self, health_pct: float) -> str:
        """Replicate the wound description lookup from a health percentage."""
        for threshold, description in WOUND_DESCRIPTIONS:
            if health_pct >= threshold:
                return description
        return WOUND_DESCRIPTIONS[-1][1]

    def test_full_health(self) -> None:
        self.assertEqual(self._get_wound_description(1.0), "healthy appearance")

    def test_half_health(self) -> None:
        self.assertEqual(self._get_wound_description(0.5), "seriously wounded")

    def test_low_health(self) -> None:
        self.assertEqual(self._get_wound_description(0.15), "barely clinging to life")

    def test_zero_health(self) -> None:
        self.assertEqual(self._get_wound_description(0.0), "incapacitated")

    def test_negative_health(self) -> None:
        self.assertEqual(self._get_wound_description(-0.1), "incapacitated")


class CharacterVitalsHealthTests(TestCase):
    """Tests for health fields and computed properties on CharacterVitals."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()

    def test_health_and_max_health_fields(self) -> None:
        vitals = CharacterVitals.objects.create(
            character_sheet=self.sheet, health=80, max_health=100
        )
        assert vitals.health == 80
        assert vitals.max_health == 100

    def test_health_defaults_to_zero(self) -> None:
        vitals = CharacterVitals.objects.create(character_sheet=self.sheet)
        assert vitals.health == 0
        assert vitals.max_health == 0

    def test_dying_final_round_default(self) -> None:
        vitals = CharacterVitals.objects.create(character_sheet=self.sheet)
        assert vitals.dying_final_round is False

    def test_health_percentage_normal(self) -> None:
        vitals = CharacterVitals(health=75, max_health=100)
        assert vitals.health_percentage == 0.75

    def test_health_percentage_zero_max(self) -> None:
        vitals = CharacterVitals(health=0, max_health=0)
        assert vitals.health_percentage == 0.0

    def test_health_percentage_negative_clamped(self) -> None:
        vitals = CharacterVitals(health=-10, max_health=100)
        assert vitals.health_percentage == 0.0

    def test_wound_description_full_health(self) -> None:
        vitals = CharacterVitals(health=100, max_health=100)
        assert vitals.wound_description == "healthy appearance"

    def test_wound_description_half_health(self) -> None:
        vitals = CharacterVitals(health=50, max_health=100)
        assert vitals.wound_description == "seriously wounded"

    def test_wound_description_zero_health(self) -> None:
        vitals = CharacterVitals(health=0, max_health=100)
        assert vitals.wound_description == "incapacitated"
