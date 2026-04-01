"""Tests for anima cost calculation and deduction services."""

from decimal import Decimal

from django.test import TestCase

from world.magic.factories import CharacterAnimaFactory, TechniqueFactory, WarpConfigFactory
from world.magic.services import (
    calculate_effective_anima_cost,
    calculate_warp_severity,
    deduct_anima,
    get_runtime_technique_stats,
    get_warp_warning,
    select_mishap_pool,
)
from world.magic.types import RuntimeTechniqueStats


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


class CalculateWarpSeverityTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        from world.checks.factories import CheckTypeFactory

        cls.check_type = CheckTypeFactory()
        cls.config = WarpConfigFactory(
            warp_threshold_ratio=Decimal("0.30"),
            severity_scale=10,
            deficit_scale=5,
            resilience_check_type=cls.check_type,
            base_check_difficulty=15,
        )

    def test_above_threshold_no_severity(self) -> None:
        result = calculate_warp_severity(
            current_anima=50, max_anima=100, deficit=0, config=self.config
        )
        assert result == 0

    def test_at_threshold_no_severity(self) -> None:
        result = calculate_warp_severity(
            current_anima=30, max_anima=100, deficit=0, config=self.config
        )
        assert result == 0

    def test_below_threshold_produces_severity(self) -> None:
        result = calculate_warp_severity(
            current_anima=15, max_anima=100, deficit=0, config=self.config
        )
        assert result > 0

    def test_empty_anima_max_depletion_severity(self) -> None:
        result = calculate_warp_severity(
            current_anima=0, max_anima=100, deficit=0, config=self.config
        )
        assert result == 10  # ceil(10 * 1.0)

    def test_deficit_adds_severity(self) -> None:
        no_deficit = calculate_warp_severity(
            current_anima=0, max_anima=100, deficit=0, config=self.config
        )
        with_deficit = calculate_warp_severity(
            current_anima=0, max_anima=100, deficit=10, config=self.config
        )
        assert with_deficit == no_deficit + 50  # ceil(5 * 10)

    def test_severity_scales_with_depletion(self) -> None:
        mild = calculate_warp_severity(
            current_anima=20, max_anima=100, deficit=0, config=self.config
        )
        severe = calculate_warp_severity(
            current_anima=5, max_anima=100, deficit=0, config=self.config
        )
        assert severe > mild


class GetWarpWarningTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        from evennia_extensions.factories import CharacterFactory
        from world.conditions.factories import (
            ConditionStageFactory,
            ConditionTemplateFactory,
        )
        from world.magic.audere import ANIMA_WARP_CONDITION_NAME

        cls.character = CharacterFactory()
        cls.warp_template = ConditionTemplateFactory(
            name=ANIMA_WARP_CONDITION_NAME,
            has_progression=True,
            is_stackable=False,
        )
        cls.stage1 = ConditionStageFactory(
            condition=cls.warp_template,
            stage_order=1,
            name="Strain",
            severity_threshold=1,
            consequence_pool=None,
        )

    def test_no_warp_returns_none(self) -> None:
        assert get_warp_warning(self.character) is None

    def test_warp_present_returns_warning(self) -> None:
        from world.conditions.services import apply_condition

        result = apply_condition(self.character, self.warp_template)
        result.instance.current_stage = self.stage1
        result.instance.save(update_fields=["current_stage"])
        warning = get_warp_warning(self.character)
        assert warning is not None
        assert warning.stage_name == "Strain"
        assert not warning.has_death_risk


class SelectMishapPoolTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        from actions.factories import ConsequencePoolFactory
        from world.magic.factories import MishapPoolTierFactory

        cls.minor_pool = ConsequencePoolFactory(name="Minor Mishaps")
        cls.severe_pool = ConsequencePoolFactory(name="Severe Mishaps")
        MishapPoolTierFactory(min_deficit=1, max_deficit=5, consequence_pool=cls.minor_pool)
        MishapPoolTierFactory(min_deficit=6, max_deficit=None, consequence_pool=cls.severe_pool)

    def test_no_match_returns_none(self) -> None:
        assert select_mishap_pool(0) is None

    def test_low_deficit_returns_minor(self) -> None:
        assert select_mishap_pool(3) == self.minor_pool

    def test_high_deficit_returns_severe(self) -> None:
        assert select_mishap_pool(10) == self.severe_pool

    def test_boundary_returns_correct_tier(self) -> None:
        assert select_mishap_pool(5) == self.minor_pool
        assert select_mishap_pool(6) == self.severe_pool
