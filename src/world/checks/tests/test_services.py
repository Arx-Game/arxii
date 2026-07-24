"""Tests for check resolution services."""

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import (
    CheckCategoryFactory,
    CheckTypeAspectFactory,
    CheckTypeCapabilityModifierFactory,
    CheckTypeFactory,
    CheckTypeTraitFactory,
    create_resistance_check_types,
)
from world.checks.services import (
    _calculate_aspect_bonus,
    _calculate_capability_points,
    _compute_check_breakdown,
    chart_has_success_outcomes,
    compute_resist_increment,
    perform_check,
    preview_check_difficulty,
)
from world.classes.factories import PathFactory
from world.classes.models import Aspect, PathAspect, PathStage
from world.conditions.factories import CapabilityTypeFactory
from world.progression.models import CharacterPathHistory
from world.traits.factories import CheckSystemSetupFactory
from world.traits.models import (
    CharacterTraitValue,
    CheckRank,
    PointConversionRange,
    ResultChart,
    Trait,
    TraitCategory,
    TraitType,
)


class CalculateAspectBonusTests(TestCase):
    """Test aspect bonus calculation from path weights."""

    @classmethod
    def setUpTestData(cls):
        cls.character = CharacterSheetFactory().character
        cls.path = PathFactory(name="TestSpyPath", stage=PathStage.PROSPECT, minimum_level=1)
        cls.intrigue = Aspect.objects.create(name="test_svc_intrigue")
        cls.subterfuge = Aspect.objects.create(name="test_svc_subterfuge")
        PathAspect.objects.create(character_path=cls.path, aspect=cls.intrigue, weight=2)
        PathAspect.objects.create(character_path=cls.path, aspect=cls.subterfuge, weight=1)
        CharacterPathHistory.objects.create(character=cls.character.sheet_data, path=cls.path)
        cls.check_type = CheckTypeFactory(name="TestSpyCheck")

    def test_aspect_bonus_with_matching_path(self):
        """Aspect bonus = sum(check_weight * path_weight * level) truncated to int."""
        CheckTypeAspectFactory(
            check_type=self.check_type,
            aspect=self.intrigue,
            weight=Decimal("1.0"),
        )
        CheckTypeAspectFactory(
            check_type=self.check_type,
            aspect=self.subterfuge,
            weight=Decimal("0.5"),
        )
        # Level 3: intrigue = int(1.0 * 2 * 3) = 6, subterfuge = int(0.5 * 1 * 3) = 1
        bonus = _calculate_aspect_bonus(self.character, self.check_type, level=3)
        assert bonus == 7

    def test_aspect_bonus_zero_with_no_path(self):
        other_char = CharacterFactory()
        CheckTypeAspectFactory(
            check_type=self.check_type,
            aspect=self.intrigue,
            weight=Decimal("1.0"),
        )
        bonus = _calculate_aspect_bonus(other_char, self.check_type, level=1)
        assert bonus == 0

    def test_aspect_bonus_zero_with_no_matching_aspects(self):
        unrelated = Aspect.objects.create(name="test_svc_unrelated")
        check = CheckTypeFactory(name="UnrelatedCheck")
        CheckTypeAspectFactory(check_type=check, aspect=unrelated, weight=Decimal("1.0"))
        bonus = _calculate_aspect_bonus(self.character, self.check_type, level=3)
        # self.check_type has no aspects at this point (other tests use setUpTestData
        # but this test uses a different check_type)
        assert bonus == 0

    def test_aspect_bonus_truncates_to_int(self):
        check = CheckTypeFactory(name="TruncateCheck")
        CheckTypeAspectFactory(
            check_type=check,
            aspect=self.subterfuge,
            weight=Decimal("0.75"),
        )
        # 0.75 * 1 * 3 = 2.25 -> int = 2
        bonus = _calculate_aspect_bonus(self.character, check, level=3)
        assert bonus == 2


class CalculateCapabilityPointsTests(TestCase):
    """Test _calculate_capability_points: authored CheckTypeCapabilityModifier folding (#2505)."""

    @classmethod
    def setUpTestData(cls):
        cls.check_type = CheckTypeFactory(name="test_svc_capability_check")
        cls.capability = CapabilityTypeFactory(name="test_svc_fire_control", innate_baseline=5)

    def test_authored_row_shifts_points_by_weighted_value(self):
        """An authored row contributes int(weight * effective_capability_value)."""
        character = CharacterFactory()
        CharacterSheetFactory(character=character)
        CheckTypeCapabilityModifierFactory(
            check_type=self.check_type,
            capability=self.capability,
            weight=Decimal("2.0"),
        )
        # innate_baseline=5, weight=2.0 -> int(5 * 2.0) == 10
        points = _calculate_capability_points(character, self.check_type)
        assert points == 10

    def test_no_authored_row_returns_zero_even_with_huge_capability_value(self):
        """CURATED GATE: a huge capability value has zero effect with no authored row."""
        character = CharacterFactory()
        CharacterSheetFactory(character=character)
        huge_capability = CapabilityTypeFactory(
            name="test_svc_huge_unlisted_capability", innate_baseline=99999
        )
        # No CheckTypeCapabilityModifier links huge_capability to self.check_type.
        assert huge_capability.innate_baseline == 99999
        points = _calculate_capability_points(character, self.check_type)
        assert points == 0

    def test_weight_rounding_truncates_toward_zero(self):
        """weight=0.5 truncates the product toward zero."""
        character = CharacterFactory()
        CharacterSheetFactory(character=character)
        odd_capability = CapabilityTypeFactory(name="test_svc_odd_capability", innate_baseline=3)
        CheckTypeCapabilityModifierFactory(
            check_type=self.check_type,
            capability=odd_capability,
            weight=Decimal("0.5"),
        )
        # 0.5 * 3 = 1.5 -> int = 1
        points = _calculate_capability_points(character, self.check_type)
        assert points == 1

    def test_sheetless_character_returns_zero_without_raising(self):
        """A character with no CharacterSheet (sheet_data) contributes 0, never raises."""
        character = CharacterFactory()
        # No CharacterSheetFactory(character=character) — sheet_data is absent.
        CheckTypeCapabilityModifierFactory(
            check_type=self.check_type,
            capability=self.capability,
            weight=Decimal("2.0"),
        )
        points = _calculate_capability_points(character, self.check_type)
        assert points == 0

    def test_folds_into_compute_check_breakdown_total_points(self):
        """capability_points is folded into total_points exactly like trait_points."""
        character = CharacterFactory()
        CharacterSheetFactory(character=character)
        CheckTypeCapabilityModifierFactory(
            check_type=self.check_type,
            capability=self.capability,
            weight=Decimal("2.0"),
        )
        breakdown = _compute_check_breakdown(
            character,
            self.check_type,
            target_difficulty=0,
            extra_modifiers=0,
            effort_level=None,
            fatigue_penalty=0,
            specialization=None,
        )
        assert breakdown.capability_points == 10
        assert breakdown.total_points == 10


class PerformCheckTests(TestCase):
    """Test the full check resolution pipeline."""

    @classmethod
    def setUpTestData(cls):
        Trait.flush_instance_cache()
        CheckSystemSetupFactory.create()
        # Create PointConversionRange for stats (CheckSystemSetupFactory only creates
        # outcomes and charts, not conversion ranges or ranks)
        PointConversionRange.objects.get_or_create(
            trait_type=TraitType.STAT,
            min_value=1,
            defaults={"max_value": 100, "points_per_level": 1},
        )
        # Create CheckRank entries for the point-to-rank pipeline
        for rank_val, min_pts, name in [
            (0, 0, "TestNone"),
            (1, 10, "TestNovice"),
            (2, 25, "TestCompetent"),
            (3, 50, "TestExpert"),
        ]:
            CheckRank.objects.get_or_create(
                rank=rank_val,
                defaults={"min_points": min_pts, "name": name},
            )
        cls.character = CharacterSheetFactory().character
        cls.strength, _ = Trait.objects.get_or_create(
            name="check_test_strength",
            defaults={
                "trait_type": TraitType.STAT,
                "category": TraitCategory.PHYSICAL,
            },
        )
        cls.category = CheckCategoryFactory(name="check_test_combat")
        cls.check_type = CheckTypeFactory(name="check_test_power_strike", category=cls.category)
        CheckTypeTraitFactory(
            check_type=cls.check_type,
            trait=cls.strength,
            weight=Decimal("1.0"),
        )

    def setUp(self):
        Trait.flush_instance_cache()
        CharacterTraitValue.flush_instance_cache()
        ResultChart.clear_cache()

    def test_perform_check_returns_check_result(self):
        from world.checks.types import CheckResult

        CharacterTraitValue.objects.create(
            character=self.character.sheet_data, trait=self.strength, value=30
        )
        result = perform_check(self.character, self.check_type, target_difficulty=0)
        assert isinstance(result, CheckResult)
        assert result.check_type == self.check_type
        assert result.trait_points > 0

    @patch("world.checks.services.random.randint", return_value=50)
    def test_perform_check_with_fixed_roll(self, mock_randint):
        CharacterTraitValue.objects.create(
            character=self.character.sheet_data, trait=self.strength, value=30
        )
        result = perform_check(self.character, self.check_type, target_difficulty=0)
        assert result.outcome is not None
        mock_randint.assert_called_once_with(1, 100)

    def test_perform_check_with_extra_modifiers(self):
        CharacterTraitValue.objects.create(
            character=self.character.sheet_data, trait=self.strength, value=30
        )
        result_base = perform_check(self.character, self.check_type, target_difficulty=0)
        result_boosted = perform_check(
            self.character,
            self.check_type,
            target_difficulty=0,
            extra_modifiers=50,
        )
        assert result_boosted.total_points > result_base.total_points


class PerformCheckEffortFatigueTests(TestCase):
    """Test effort level and fatigue penalty integration with perform_check."""

    @classmethod
    def setUpTestData(cls):
        Trait.flush_instance_cache()
        CheckSystemSetupFactory.create()
        PointConversionRange.objects.get_or_create(
            trait_type=TraitType.STAT,
            min_value=1,
            defaults={"max_value": 100, "points_per_level": 1},
        )
        for rank_val, min_pts, name in [
            (0, 0, "EffortNone"),
            (1, 10, "EffortNovice"),
            (2, 25, "EffortCompetent"),
            (3, 50, "EffortExpert"),
        ]:
            CheckRank.objects.get_or_create(
                rank=rank_val,
                defaults={"min_points": min_pts, "name": name},
            )
        cls.character = CharacterSheetFactory().character
        cls.strength, _ = Trait.objects.get_or_create(
            name="effort_test_strength",
            defaults={
                "trait_type": TraitType.STAT,
                "category": TraitCategory.PHYSICAL,
            },
        )
        cls.category = CheckCategoryFactory(name="effort_test_combat")
        cls.check_type = CheckTypeFactory(name="effort_test_strike", category=cls.category)
        CheckTypeTraitFactory(
            check_type=cls.check_type,
            trait=cls.strength,
            weight=Decimal("1.0"),
        )

    def setUp(self):
        Trait.flush_instance_cache()
        CharacterTraitValue.flush_instance_cache()
        ResultChart.clear_cache()

    def test_very_low_applies_minus_three(self):
        """Very low effort applies -3 modifier to total points."""
        CharacterTraitValue.objects.create(
            character=self.character.sheet_data, trait=self.strength, value=30
        )
        result_base = perform_check(self.character, self.check_type, target_difficulty=0)
        result_very_low = perform_check(
            self.character, self.check_type, target_difficulty=0, effort_level="very_low"
        )
        assert result_very_low.total_points == result_base.total_points - 3

    def test_low_applies_minus_one(self):
        """Low effort applies -1 modifier to total points."""
        CharacterTraitValue.objects.create(
            character=self.character.sheet_data, trait=self.strength, value=30
        )
        result_base = perform_check(self.character, self.check_type, target_difficulty=0)
        result_low = perform_check(
            self.character, self.check_type, target_difficulty=0, effort_level="low"
        )
        assert result_low.total_points == result_base.total_points - 1

    def test_medium_effort_no_modifier(self):
        """Medium effort applies 0 modifier to total points."""
        CharacterTraitValue.objects.create(
            character=self.character.sheet_data, trait=self.strength, value=30
        )
        result_base = perform_check(self.character, self.check_type, target_difficulty=0)
        result_medium = perform_check(
            self.character, self.check_type, target_difficulty=0, effort_level="medium"
        )
        assert result_medium.total_points == result_base.total_points

    def test_high_applies_plus_two(self):
        """High effort applies +2 modifier to total points."""
        CharacterTraitValue.objects.create(
            character=self.character.sheet_data, trait=self.strength, value=30
        )
        result_base = perform_check(self.character, self.check_type, target_difficulty=0)
        result_high = perform_check(
            self.character, self.check_type, target_difficulty=0, effort_level="high"
        )
        assert result_high.total_points == result_base.total_points + 2

    def test_extreme_applies_plus_four(self):
        """Extreme effort applies +4 modifier to total points."""
        CharacterTraitValue.objects.create(
            character=self.character.sheet_data, trait=self.strength, value=30
        )
        result_base = perform_check(self.character, self.check_type, target_difficulty=0)
        result_extreme = perform_check(
            self.character, self.check_type, target_difficulty=0, effort_level="extreme"
        )
        assert result_extreme.total_points == result_base.total_points + 4

    def test_fatigue_penalty_applied(self):
        """Fatigue penalty is subtracted from total points."""
        CharacterTraitValue.objects.create(
            character=self.character.sheet_data, trait=self.strength, value=30
        )
        result_base = perform_check(self.character, self.check_type, target_difficulty=0)
        result_fatigued = perform_check(
            self.character, self.check_type, target_difficulty=0, fatigue_penalty=-3
        )
        assert result_fatigued.total_points == result_base.total_points - 3

    def test_effort_and_fatigue_combined(self):
        """Both effort modifier and fatigue penalty apply together."""
        CharacterTraitValue.objects.create(
            character=self.character.sheet_data, trait=self.strength, value=30
        )
        result_base = perform_check(self.character, self.check_type, target_difficulty=0)
        result_combined = perform_check(
            self.character,
            self.check_type,
            target_difficulty=0,
            effort_level="extreme",
            fatigue_penalty=-3,
        )
        # +4 from extreme, -3 from fatigue = net +1
        assert result_combined.total_points == result_base.total_points + 1

    def test_no_effort_level_preserves_behavior(self):
        """Omitting effort_level preserves existing behavior (no modifier)."""
        CharacterTraitValue.objects.create(
            character=self.character.sheet_data, trait=self.strength, value=30
        )
        result_default = perform_check(self.character, self.check_type, target_difficulty=0)
        result_none = perform_check(
            self.character, self.check_type, target_difficulty=0, effort_level=None
        )
        assert result_none.total_points == result_default.total_points


class PreviewCheckDifficultyTests(TestCase):
    """Test preview_check_difficulty returns rank difference without rolling."""

    @classmethod
    def setUpTestData(cls):
        Trait.flush_instance_cache()
        CheckSystemSetupFactory.create()
        PointConversionRange.objects.get_or_create(
            trait_type=TraitType.STAT,
            min_value=1,
            defaults={"max_value": 100, "points_per_level": 1},
        )
        for rank_val, min_pts, name in [
            (0, 0, "PrevNone"),
            (1, 10, "PrevNovice"),
            (2, 25, "PrevCompetent"),
            (3, 50, "PrevExpert"),
        ]:
            CheckRank.objects.get_or_create(
                rank=rank_val,
                defaults={"min_points": min_pts, "name": name},
            )
        cls.character = CharacterSheetFactory().character
        cls.strength, _ = Trait.objects.get_or_create(
            name="preview_strength",
            defaults={
                "trait_type": TraitType.STAT,
                "category": TraitCategory.PHYSICAL,
            },
        )
        cls.category = CheckCategoryFactory(name="preview_combat")
        cls.check_type = CheckTypeFactory(name="preview_strike", category=cls.category)
        CheckTypeTraitFactory(
            check_type=cls.check_type,
            trait=cls.strength,
            weight=Decimal("1.0"),
        )

    def setUp(self):
        Trait.flush_instance_cache()
        CharacterTraitValue.flush_instance_cache()

    def test_preview_returns_positive_when_strong(self):
        """Character with high trait points gets positive rank difference."""
        CharacterTraitValue.objects.create(
            character=self.character.sheet_data, trait=self.strength, value=60
        )
        rank_diff = preview_check_difficulty(self.character, self.check_type, target_difficulty=0)
        assert rank_diff > 0

    def test_preview_returns_zero_when_equal(self):
        """Character with no traits vs zero difficulty gives rank diff 0."""
        rank_diff = preview_check_difficulty(self.character, self.check_type, target_difficulty=0)
        assert rank_diff == 0

    def test_preview_returns_negative_when_weak(self):
        """Character with low traits vs high difficulty gives negative rank diff."""
        CharacterTraitValue.objects.create(
            character=self.character.sheet_data, trait=self.strength, value=5
        )
        rank_diff = preview_check_difficulty(self.character, self.check_type, target_difficulty=50)
        assert rank_diff < 0

    def test_extra_modifiers_increase_rank_diff(self):
        """Extra modifiers boost the character's side of the calculation."""
        CharacterTraitValue.objects.create(
            character=self.character.sheet_data, trait=self.strength, value=5
        )
        base = preview_check_difficulty(self.character, self.check_type, target_difficulty=0)
        boosted = preview_check_difficulty(
            self.character, self.check_type, target_difficulty=0, extra_modifiers=100
        )
        assert boosted >= base


class ChartHasSuccessOutcomesTests(TestCase):
    """Test chart_has_success_outcomes checks for positive success_level."""

    @classmethod
    def setUpTestData(cls):
        CheckSystemSetupFactory.create()

    def setUp(self):
        ResultChart.clear_cache()

    def test_chart_with_success(self):
        """Charts that include success outcomes return True."""
        # CheckSystemSetupFactory creates charts at -2, -1, 0, 1, 2 — all have successes
        assert chart_has_success_outcomes(0) is True

    def test_chart_with_success_at_hard_difficulty(self):
        """Hard difficulty charts still have success outcomes."""
        assert chart_has_success_outcomes(2) is True

    def test_no_chart_returns_false(self):
        """Rank differences with no chart at all return False."""
        # Clear cache and remove all charts to test missing chart
        ResultChart.clear_cache()
        ResultChart.objects.all().delete()
        assert chart_has_success_outcomes(999) is False


class ComputeResistIncrementTests(TestCase):
    """Test compute_resist_increment: Composure check type + effort level → resist increment."""

    @classmethod
    def setUpTestData(cls):
        Trait.flush_instance_cache()
        # PointConversionRange is required for _calculate_trait_points to convert trait
        # values into points. weight=1.0 on willpower, so we need STAT conversion.
        PointConversionRange.objects.get_or_create(
            trait_type=TraitType.STAT,
            min_value=1,
            defaults={"max_value": 100, "points_per_level": 1},
        )
        # Seed the Composure CheckType + willpower trait weight via the factory helper.
        create_resistance_check_types()
        cls.character = CharacterSheetFactory().character
        # Resolve the willpower trait seeded by create_resistance_check_types().
        cls.willpower_trait, _ = Trait.objects.get_or_create(
            name="willpower",
            defaults={
                "trait_type": TraitType.STAT,
                "category": TraitCategory.GENERAL,
            },
        )

    def setUp(self):
        Trait.flush_instance_cache()
        CharacterTraitValue.flush_instance_cache()

    def test_high_effort_greater_than_low_effort(self):
        """A defender with willpower gets more resist increment at high effort than low."""
        CharacterTraitValue.objects.create(
            character=self.character.sheet_data, trait=self.willpower_trait, value=20
        )
        increment_high = compute_resist_increment(self.character, resist_effort_level="high")
        increment_low = compute_resist_increment(self.character, resist_effort_level="low")
        assert increment_high > 0
        assert increment_high > increment_low

    def test_returns_zero_when_no_composure_check_type(self):
        """When Composure CheckType does not exist, compute_resist_increment returns 0."""
        from world.checks.models import CheckType

        CheckType.objects.filter(name="Composure").delete()
        result = compute_resist_increment(self.character, resist_effort_level="high")
        assert result == 0
