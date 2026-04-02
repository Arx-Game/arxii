"""Tests for fatigue models."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.fatigue.models import FatiguePool


class FatiguePoolTests(TestCase):
    """Tests for FatiguePool model."""

    def setUp(self) -> None:
        """Clear SharedMemoryModel cache between tests."""
        FatiguePool.flush_instance_cache()

    @classmethod
    def setUpTestData(cls) -> None:
        """Create shared test data."""
        cls.sheet = CharacterSheetFactory()

    def test_creation_defaults(self) -> None:
        """FatiguePool created with all pools at 0 and flags False."""
        pool = FatiguePool.objects.create(character=self.sheet)
        assert pool.physical_current == 0
        assert pool.social_current == 0
        assert pool.mental_current == 0
        assert pool.well_rested is False
        assert pool.rested_today is False
        assert pool.dawn_deferred is False

    def test_get_current_physical(self) -> None:
        """get_current returns physical fatigue value."""
        pool = FatiguePool.objects.create(character=self.sheet, physical_current=15)
        assert pool.get_current("physical") == 15

    def test_get_current_social(self) -> None:
        """get_current returns social fatigue value."""
        pool = FatiguePool.objects.create(character=self.sheet, social_current=8)
        assert pool.get_current("social") == 8

    def test_get_current_mental(self) -> None:
        """get_current returns mental fatigue value."""
        pool = FatiguePool.objects.create(character=self.sheet, mental_current=22)
        assert pool.get_current("mental") == 22

    def test_set_current_updates_field(self) -> None:
        """set_current updates the correct field."""
        pool = FatiguePool.objects.create(character=self.sheet)
        pool.set_current("physical", 10)
        assert pool.physical_current == 10

        pool.set_current("social", 5)
        assert pool.social_current == 5

        pool.set_current("mental", 20)
        assert pool.mental_current == 20

    def test_set_current_clamps_to_zero(self) -> None:
        """set_current clamps negative values to 0."""
        pool = FatiguePool.objects.create(character=self.sheet)
        pool.set_current("physical", -5)
        assert pool.physical_current == 0

    def test_str_representation(self) -> None:
        """__str__ shows character and all pool values."""
        pool = FatiguePool.objects.create(
            character=self.sheet,
            physical_current=10,
            social_current=5,
            mental_current=3,
        )
        result = str(pool)
        assert "Fatigue:" in result
        assert "P:10" in result
        assert "S:5" in result
        assert "M:3" in result
