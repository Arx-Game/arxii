"""Tests for resolve_perception_check — the canonical perception-check seam (#2997)."""

from unittest.mock import patch

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.perception_constants import (
    PERCEPTION_CHECK_TYPE_NAME,
    PERCEPTION_DIFFICULTY_EASY,
    PERCEPTION_DIFFICULTY_HARD,
    PERCEPTION_DIFFICULTY_STANDARD,
)
from world.checks.perception_services import resolve_perception_check
from world.skills.factories import SpecializationFactory


class ResolvePerceptionCheckTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.check_type = CheckTypeFactory(name=PERCEPTION_CHECK_TYPE_NAME)

    def test_passes_character_check_type_and_difficulty_to_perform_check(self):
        """The seam resolves the seeded Perception CheckType and forwards difficulty."""
        with patch("world.checks.perception_services.perform_check") as mock_perform:
            resolve_perception_check(self.sheet, difficulty=PERCEPTION_DIFFICULTY_STANDARD)

        mock_perform.assert_called_once_with(
            self.sheet.character,
            self.check_type,
            target_difficulty=PERCEPTION_DIFFICULTY_STANDARD,
            specialization=None,
        )

    def test_passes_specialization_through_unchanged(self):
        """An owned specialization is forwarded, not swallowed or re-derived."""
        specialization = SpecializationFactory()

        with patch("world.checks.perception_services.perform_check") as mock_perform:
            resolve_perception_check(
                self.sheet,
                difficulty=PERCEPTION_DIFFICULTY_EASY,
                specialization=specialization,
            )

        mock_perform.assert_called_once_with(
            self.sheet.character,
            self.check_type,
            target_difficulty=PERCEPTION_DIFFICULTY_EASY,
            specialization=specialization,
        )

    def test_returns_perform_check_result(self):
        """The seam is a pure delegation — its return value IS perform_check's."""
        with patch("world.checks.perception_services.perform_check") as mock_perform:
            mock_perform.return_value = "sentinel-result"
            result = resolve_perception_check(self.sheet, difficulty=PERCEPTION_DIFFICULTY_HARD)

        assert result == "sentinel-result"

    def test_missing_check_type_raises_value_error(self):
        """If the 'Perception' CheckType is not seeded/active, fail loudly."""
        self.check_type.is_active = False
        self.check_type.save()

        with self.assertRaises(ValueError) as ctx:
            resolve_perception_check(self.sheet, difficulty=PERCEPTION_DIFFICULTY_STANDARD)
        assert PERCEPTION_CHECK_TYPE_NAME in str(ctx.exception)


class PerceptionDifficultyConstantsTests(TestCase):
    def test_constants_exist_and_are_ordered(self):
        """EASY < STANDARD < HARD — placeholder magnitudes, but internally consistent."""
        assert PERCEPTION_DIFFICULTY_EASY < PERCEPTION_DIFFICULTY_STANDARD
        assert PERCEPTION_DIFFICULTY_STANDARD < PERCEPTION_DIFFICULTY_HARD
