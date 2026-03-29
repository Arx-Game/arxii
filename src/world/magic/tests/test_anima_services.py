"""Tests for anima cost calculation and deduction services."""

from django.test import TestCase

from world.magic.factories import CharacterAnimaFactory, TechniqueFactory
from world.magic.services import (
    calculate_effective_anima_cost,
    deduct_anima,
    get_overburn_severity,
    get_runtime_technique_stats,
)
from world.magic.types import OverburnSeverity, RuntimeTechniqueStats


class RuntimeStatsTests(TestCase):
    """Tests for get_runtime_technique_stats — MVP returns base values."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.technique = TechniqueFactory(intensity=10, control=7)

    def test_returns_base_values(self) -> None:
        stats = get_runtime_technique_stats(self.technique, character=None)
        assert isinstance(stats, RuntimeTechniqueStats)
        assert stats.intensity == 10
        assert stats.control == 7


class AnimaCostTests(TestCase):
    """Tests for calculate_effective_anima_cost."""

    def test_balanced_intensity_control(self) -> None:
        """Equal intensity and control = base cost unchanged."""
        result = calculate_effective_anima_cost(
            base_cost=10,
            runtime_intensity=10,
            runtime_control=10,
            current_anima=20,
        )
        assert result.effective_cost == 10
        assert result.deficit == 0

    def test_high_control_reduces_cost(self) -> None:
        """Control exceeding intensity reduces cost."""
        result = calculate_effective_anima_cost(
            base_cost=10,
            runtime_intensity=10,
            runtime_control=15,
            current_anima=20,
        )
        assert result.effective_cost == 5
        assert result.deficit == 0

    def test_very_high_control_floors_at_zero(self) -> None:
        """Very high control can reduce cost to zero."""
        result = calculate_effective_anima_cost(
            base_cost=10,
            runtime_intensity=10,
            runtime_control=25,
            current_anima=20,
        )
        assert result.effective_cost == 0
        assert result.deficit == 0

    def test_high_intensity_increases_cost(self) -> None:
        """Intensity exceeding control increases cost."""
        result = calculate_effective_anima_cost(
            base_cost=10,
            runtime_intensity=15,
            runtime_control=10,
            current_anima=20,
        )
        assert result.effective_cost == 15
        assert result.deficit == 0

    def test_overburn_calculates_deficit(self) -> None:
        """Cost exceeding current anima produces a deficit."""
        result = calculate_effective_anima_cost(
            base_cost=10,
            runtime_intensity=25,
            runtime_control=10,
            current_anima=8,
        )
        assert result.effective_cost == 25
        assert result.deficit == 17
        assert result.is_overburn is True

    def test_exact_anima_no_overburn(self) -> None:
        """Cost exactly equal to current anima has no deficit."""
        result = calculate_effective_anima_cost(
            base_cost=10,
            runtime_intensity=10,
            runtime_control=10,
            current_anima=10,
        )
        assert result.deficit == 0
        assert result.is_overburn is False


class OverburnSeverityTests(TestCase):
    """Tests for get_overburn_severity."""

    def test_no_deficit_returns_none(self) -> None:
        assert get_overburn_severity(0) is None

    def test_small_deficit_painful(self) -> None:
        result = get_overburn_severity(3)
        assert isinstance(result, OverburnSeverity)
        assert result.can_cause_death is False

    def test_large_deficit_can_cause_death(self) -> None:
        result = get_overburn_severity(20)
        assert isinstance(result, OverburnSeverity)
        assert result.can_cause_death is True


class DeductAnimaTests(TestCase):
    """Tests for deduct_anima with select_for_update."""

    def test_deduct_within_pool(self) -> None:
        """Deduction within available anima reduces current."""
        anima = CharacterAnimaFactory(current=10, maximum=10)
        deficit = deduct_anima(anima.character, effective_cost=7)
        anima.refresh_from_db()
        assert anima.current == 3
        assert deficit == 0

    def test_deduct_with_overburn(self) -> None:
        """Deduction exceeding pool sets current to 0, returns deficit."""
        anima = CharacterAnimaFactory(current=8, maximum=10)
        deficit = deduct_anima(anima.character, effective_cost=15)
        anima.refresh_from_db()
        assert anima.current == 0
        assert deficit == 7

    def test_deduct_zero_cost(self) -> None:
        """Zero cost deducts nothing."""
        anima = CharacterAnimaFactory(current=10, maximum=10)
        deficit = deduct_anima(anima.character, effective_cost=0)
        anima.refresh_from_db()
        assert anima.current == 10
        assert deficit == 0
