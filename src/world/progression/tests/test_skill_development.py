"""Tests for the skill development system (check-based dp awards and level-ups)."""

from django.test import TestCase
from evennia.objects.models import ObjectDB

from world.checks.models import CheckCategory, CheckType, CheckTypeTrait
from world.fatigue.constants import EffortLevel
from world.progression.models import WeeklySkillUsage, cumulative_dp_for_level
from world.progression.models.rewards import DevelopmentPoints
from world.progression.services.skill_development import (
    award_check_development,
    calculate_check_dev_points,
)
from world.traits.factories import TraitFactory
from world.traits.models import CharacterTraitValue


class CumulativeDpForLevelTest(TestCase):
    """Test the cumulative_dp_for_level helper."""

    def test_level_10_is_zero(self) -> None:
        assert cumulative_dp_for_level(10) == 0

    def test_below_10_is_zero(self) -> None:
        assert cumulative_dp_for_level(5) == 0
        assert cumulative_dp_for_level(1) == 0

    def test_level_11(self) -> None:
        # (10 - 9) * 100 = 100
        assert cumulative_dp_for_level(11) == 100

    def test_level_12(self) -> None:
        # 100 + 200 = 300
        assert cumulative_dp_for_level(12) == 300

    def test_level_13(self) -> None:
        # 100 + 200 + 300 = 600
        assert cumulative_dp_for_level(13) == 600

    def test_level_15(self) -> None:
        # 100 + 200 + 300 + 400 + 500 = 1500
        assert cumulative_dp_for_level(15) == 1500

    def test_level_20(self) -> None:
        # sum((n-9)*100 for n in range(10,20)) = 100+200+...+1000 = 5500
        assert cumulative_dp_for_level(20) == 5500


class CalculateCheckDevPointsTest(TestCase):
    """Test the calculate_check_dev_points formula."""

    def test_very_low_returns_zero(self) -> None:
        assert calculate_check_dev_points(EffortLevel.VERY_LOW, 5) == 0

    def test_low_returns_zero(self) -> None:
        assert calculate_check_dev_points(EffortLevel.LOW, 10) == 0

    def test_medium_path_level_1(self) -> None:
        # base=10, multiplier = 1 + (1//2) = 1
        assert calculate_check_dev_points(EffortLevel.MEDIUM, 1) == 10

    def test_medium_path_level_2(self) -> None:
        # base=10, multiplier = 1 + (2//2) = 2
        assert calculate_check_dev_points(EffortLevel.MEDIUM, 2) == 20

    def test_high_path_level_1(self) -> None:
        # base=20, multiplier = 1 + 0 = 1
        assert calculate_check_dev_points(EffortLevel.HIGH, 1) == 20

    def test_high_path_level_4(self) -> None:
        # base=20, multiplier = 1 + 2 = 3
        assert calculate_check_dev_points(EffortLevel.HIGH, 4) == 60

    def test_extreme_path_level_6(self) -> None:
        # base=30, multiplier = 1 + 3 = 4
        assert calculate_check_dev_points(EffortLevel.EXTREME, 6) == 120


class DevelopmentPointsAwardTest(TestCase):
    """Test DevelopmentPoints.award_points with level-up logic."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = ObjectDB.objects.create(db_key="DevTestChar")
        cls.trait = TraitFactory(name="swords_dev_test")

    def setUp(self) -> None:
        DevelopmentPoints.flush_instance_cache()
        CharacterTraitValue.flush_instance_cache()

    def test_award_no_level_up(self) -> None:
        """Awarding < 100 dp to a level-10 trait triggers no level-up."""
        dev = DevelopmentPoints.objects.create(
            character=self.character, trait=self.trait, total_earned=0
        )
        level_ups = dev.award_points(50)
        assert level_ups == []
        assert dev.total_earned == 50
        # Trait value should stay at 10
        tv = CharacterTraitValue.objects.get(character=self.character, trait=self.trait)
        assert tv.value == 10

    def test_award_single_level_up(self) -> None:
        """Awarding exactly 100 dp triggers 10->11."""
        dev = DevelopmentPoints.objects.create(
            character=self.character, trait=self.trait, total_earned=0
        )
        level_ups = dev.award_points(100)
        assert level_ups == [(10, 11)]
        tv = CharacterTraitValue.objects.get(character=self.character, trait=self.trait)
        assert tv.value == 11

    def test_award_multiple_level_ups(self) -> None:
        """Awarding 300 dp triggers 10->11 and 11->12 (thresholds: 100, 300)."""
        dev = DevelopmentPoints.objects.create(
            character=self.character, trait=self.trait, total_earned=0
        )
        level_ups = dev.award_points(300)
        assert level_ups == [(10, 11), (11, 12)]
        tv = CharacterTraitValue.objects.get(character=self.character, trait=self.trait)
        assert tv.value == 12

    def test_cumulative_award_across_calls(self) -> None:
        """Multiple small awards that cumulatively cross a threshold trigger level-up."""
        dev = DevelopmentPoints.objects.create(
            character=self.character, trait=self.trait, total_earned=0
        )
        # First award: 60 dp, no level-up
        level_ups = dev.award_points(60)
        assert level_ups == []

        # Second award: 40 dp, total now 100 -> level-up
        dev.refresh_from_db()
        level_ups = dev.award_points(40)
        assert level_ups == [(10, 11)]
        tv = CharacterTraitValue.objects.get(character=self.character, trait=self.trait)
        assert tv.value == 11

    def test_existing_trait_value_respected(self) -> None:
        """If trait is already at level 12, need cumulative dp >= 600 for level 13."""
        CharacterTraitValue.objects.create(character=self.character, trait=self.trait, value=12)
        dev = DevelopmentPoints.objects.create(
            character=self.character, trait=self.trait, total_earned=300
        )
        # At level 12, need 600 cumulative for 13. Have 300, award 250 -> 550, not enough.
        level_ups = dev.award_points(250)
        assert level_ups == []
        assert dev.total_earned == 550

        # Award 50 more -> 600, level up to 13
        dev.refresh_from_db()
        level_ups = dev.award_points(50)
        assert level_ups == [(12, 13)]


class AwardCheckDevelopmentTest(TestCase):
    """Test the award_check_development service function."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = ObjectDB.objects.create(db_key="CheckDevChar")
        cls.trait1 = TraitFactory(name="stealth_check_dev")
        cls.trait2 = TraitFactory(name="agility_check_dev")
        cls.category = CheckCategory.objects.create(name="test_dev_category")
        cls.check_type = CheckType.objects.create(
            name="sneak_dev_test",
            category=cls.category,
        )
        CheckTypeTrait.objects.create(check_type=cls.check_type, trait=cls.trait1, weight=1.0)
        CheckTypeTrait.objects.create(check_type=cls.check_type, trait=cls.trait2, weight=0.5)

    def setUp(self) -> None:
        DevelopmentPoints.flush_instance_cache()
        WeeklySkillUsage.flush_instance_cache()
        CharacterTraitValue.flush_instance_cache()
        # Clean up per-test data
        DevelopmentPoints.objects.filter(character=self.character).delete()
        WeeklySkillUsage.objects.filter(character=self.character).delete()
        CharacterTraitValue.objects.filter(character=self.character).delete()

    def test_none_effort_returns_empty(self) -> None:
        result = award_check_development(
            character=self.character,
            check_type=self.check_type,
            effort_level=None,
            path_level=1,
        )
        assert result == []

    def test_low_effort_returns_empty(self) -> None:
        result = award_check_development(
            character=self.character,
            check_type=self.check_type,
            effort_level=EffortLevel.LOW,
            path_level=1,
        )
        assert result == []

    def test_medium_effort_awards_dp(self) -> None:
        """Medium effort at path level 1 awards 10 dp to each trait."""
        result = award_check_development(
            character=self.character,
            check_type=self.check_type,
            effort_level=EffortLevel.MEDIUM,
            path_level=1,
        )
        # No level-ups (need 100 dp for 10->11)
        assert result == []

        # Check DevelopmentPoints were created
        dp1 = DevelopmentPoints.objects.get(character=self.character, trait=self.trait1)
        assert dp1.total_earned == 10
        dp2 = DevelopmentPoints.objects.get(character=self.character, trait=self.trait2)
        assert dp2.total_earned == 10

    def test_weekly_skill_usage_created(self) -> None:
        """WeeklySkillUsage rows are created/updated for each trait."""
        award_check_development(
            character=self.character,
            check_type=self.check_type,
            effort_level=EffortLevel.MEDIUM,
            path_level=1,
        )
        usages = WeeklySkillUsage.objects.filter(character=self.character)
        assert usages.count() == 2
        # Bypass SharedMemoryModel cache by using values()
        for row in usages.values("check_count", "points_earned"):
            assert row["check_count"] == 1
            assert row["points_earned"] == 10

    def test_weekly_skill_usage_accumulates(self) -> None:
        """Multiple checks accumulate in the same WeeklySkillUsage row."""
        for _ in range(3):
            award_check_development(
                character=self.character,
                check_type=self.check_type,
                effort_level=EffortLevel.MEDIUM,
                path_level=1,
            )
        # Bypass SharedMemoryModel cache by using values() directly
        usage_data = (
            WeeklySkillUsage.objects.filter(character=self.character, trait=self.trait1)
            .values("check_count", "points_earned")
            .first()
        )
        assert usage_data is not None
        assert usage_data["check_count"] == 3
        assert usage_data["points_earned"] == 30

    def test_level_up_returned(self) -> None:
        """When enough dp are accumulated, level-ups are returned."""
        # Pre-load 90 dp
        DevelopmentPoints.objects.create(
            character=self.character, trait=self.trait1, total_earned=90
        )
        DevelopmentPoints.objects.create(
            character=self.character, trait=self.trait2, total_earned=90
        )
        # Medium effort + path level 1 = 10 dp -> total 100 -> level 11
        result = award_check_development(
            character=self.character,
            check_type=self.check_type,
            effort_level=EffortLevel.MEDIUM,
            path_level=1,
        )
        assert len(result) == 2
        trait_names = {r[0] for r in result}
        assert self.trait1.name in trait_names
        assert self.trait2.name in trait_names
        for _trait_name, old_lvl, new_lvl in result:
            assert old_lvl == 10
            assert new_lvl == 11
