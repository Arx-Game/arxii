"""Tests for check resolution services."""

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.checks.factories import (
    CheckCategoryFactory,
    CheckTypeAspectFactory,
    CheckTypeFactory,
    CheckTypeTraitFactory,
)
from world.checks.services import _calculate_aspect_bonus, perform_check
from world.classes.factories import PathFactory
from world.classes.models import Aspect, PathAspect, PathStage
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
        cls.character = CharacterFactory()
        cls.path = PathFactory(name="TestSpyPath", stage=PathStage.PROSPECT, minimum_level=1)
        cls.intrigue = Aspect.objects.create(name="test_svc_intrigue")
        cls.subterfuge = Aspect.objects.create(name="test_svc_subterfuge")
        PathAspect.objects.create(character_path=cls.path, aspect=cls.intrigue, weight=2)
        PathAspect.objects.create(character_path=cls.path, aspect=cls.subterfuge, weight=1)
        CharacterPathHistory.objects.create(character=cls.character, path=cls.path)
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
        cls.character = CharacterFactory()
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

        CharacterTraitValue.objects.create(character=self.character, trait=self.strength, value=30)
        result = perform_check(self.character, self.check_type, target_difficulty=0)
        assert isinstance(result, CheckResult)
        assert result.check_type == self.check_type
        assert result.trait_points > 0

    @patch("world.checks.services.random.randint", return_value=50)
    def test_perform_check_with_fixed_roll(self, mock_randint):
        CharacterTraitValue.objects.create(character=self.character, trait=self.strength, value=30)
        result = perform_check(self.character, self.check_type, target_difficulty=0)
        assert result.outcome is not None
        mock_randint.assert_called_once_with(1, 100)

    def test_perform_check_with_extra_modifiers(self):
        CharacterTraitValue.objects.create(character=self.character, trait=self.strength, value=30)
        result_base = perform_check(self.character, self.check_type, target_difficulty=0)
        result_boosted = perform_check(
            self.character,
            self.check_type,
            target_difficulty=0,
            extra_modifiers=50,
        )
        assert result_boosted.total_points > result_base.total_points
