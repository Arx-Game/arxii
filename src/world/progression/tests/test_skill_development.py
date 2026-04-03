"""Tests for the skill development system (check-based dp awards and level-ups)."""

import datetime

from django.test import TestCase
from evennia.objects.models import ObjectDB

from world.checks.models import CheckCategory, CheckType, CheckTypeTrait
from world.classes.factories import CharacterClassFactory
from world.fatigue.constants import EffortLevel
from world.progression.models import (
    DevelopmentTransaction,
    WeeklySkillUsage,
    cumulative_dp_for_level,
)
from world.progression.models.rewards import DevelopmentPoints
from world.progression.services.skill_development import (
    apply_skill_rust,
    award_check_development,
    calculate_check_dev_points,
    process_weekly_skill_development,
)
from world.progression.types import DevelopmentSource
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


class RustDebtPayoffTest(TestCase):
    """Test that award_points pays off rust_debt before counting toward advancement."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = ObjectDB.objects.create(db_key="RustDebtChar")
        cls.trait = TraitFactory(name="rust_debt_test")

    def setUp(self) -> None:
        DevelopmentPoints.flush_instance_cache()
        CharacterTraitValue.flush_instance_cache()
        DevelopmentPoints.objects.filter(character=self.character).delete()
        CharacterTraitValue.objects.filter(character=self.character).delete()

    def test_full_payoff_remainder_counts(self) -> None:
        """If rust_debt=30 and we award 50, 30 pays debt and 20 goes to total_earned."""
        dev = DevelopmentPoints.objects.create(
            character=self.character, trait=self.trait, total_earned=0, rust_debt=30
        )
        dev.award_points(50)
        dev.refresh_from_db()
        assert dev.rust_debt == 0
        assert dev.total_earned == 20

    def test_partial_payoff(self) -> None:
        """If rust_debt=50 and we award 30, debt drops to 20 and no dp toward advancement."""
        dev = DevelopmentPoints.objects.create(
            character=self.character, trait=self.trait, total_earned=0, rust_debt=50
        )
        dev.award_points(30)
        dev.refresh_from_db()
        assert dev.rust_debt == 20
        assert dev.total_earned == 0

    def test_exact_payoff(self) -> None:
        """If rust_debt equals the award, debt goes to 0, no dp toward advancement."""
        dev = DevelopmentPoints.objects.create(
            character=self.character, trait=self.trait, total_earned=0, rust_debt=40
        )
        dev.award_points(40)
        dev.refresh_from_db()
        assert dev.rust_debt == 0
        assert dev.total_earned == 0

    def test_no_level_up_while_paying_debt(self) -> None:
        """A character with rust_debt doesn't level up even if award is large enough."""
        dev = DevelopmentPoints.objects.create(
            character=self.character, trait=self.trait, total_earned=90, rust_debt=50
        )
        # Need 100 total_earned for level 11. Have 90 + award 50.
        # But 50 of the award pays debt, so total_earned stays at 90.
        level_ups = dev.award_points(50)
        assert level_ups == []
        dev.refresh_from_db()
        assert dev.rust_debt == 0
        assert dev.total_earned == 90

    def test_no_debt_works_normally(self) -> None:
        """When rust_debt is 0, award_points behaves as before."""
        dev = DevelopmentPoints.objects.create(
            character=self.character, trait=self.trait, total_earned=0, rust_debt=0
        )
        level_ups = dev.award_points(100)
        assert level_ups == [(10, 11)]
        dev.refresh_from_db()
        assert dev.rust_debt == 0
        assert dev.total_earned == 100


class ApplySkillRustTest(TestCase):
    """Test the apply_skill_rust function."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = ObjectDB.objects.create(db_key="RustChar")
        cls.trait = TraitFactory(name="rust_apply_test")

    def setUp(self) -> None:
        DevelopmentPoints.flush_instance_cache()
        DevelopmentPoints.objects.filter(character=self.character).delete()

    def test_basic_rust_amount(self) -> None:
        """Rust = character_level + 5."""
        dev = DevelopmentPoints.objects.create(
            character=self.character, trait=self.trait, total_earned=100, rust_debt=0
        )
        result = apply_skill_rust(dev, character_level=3, trait_level=11)
        # 3 + 5 = 8, cap = (11 - 9) * 100 = 200, so 8 applies
        assert result == 8
        dev.refresh_from_db()
        assert dev.rust_debt == 8

    def test_rust_capped_at_level_cost(self) -> None:
        """Rust cannot exceed the cost of the current level."""
        dev = DevelopmentPoints.objects.create(
            character=self.character, trait=self.trait, total_earned=100, rust_debt=0
        )
        # trait_level=11, cost = (11-9)*100 = 200
        # character_level=300, rust = 305, capped at 200
        result = apply_skill_rust(dev, character_level=300, trait_level=11)
        assert result == 200
        dev.refresh_from_db()
        assert dev.rust_debt == 200

    def test_no_rust_below_base_level(self) -> None:
        """Skills at or below level 10 don't get rust."""
        dev = DevelopmentPoints.objects.create(
            character=self.character, trait=self.trait, total_earned=0, rust_debt=0
        )
        result = apply_skill_rust(dev, character_level=5, trait_level=10)
        assert result == 0
        dev.refresh_from_db()
        assert dev.rust_debt == 0

    def test_no_rust_at_level_5(self) -> None:
        """Skills below the base level don't get rust."""
        dev = DevelopmentPoints.objects.create(
            character=self.character, trait=self.trait, total_earned=0, rust_debt=0
        )
        result = apply_skill_rust(dev, character_level=10, trait_level=5)
        assert result == 0

    def test_rust_accumulates(self) -> None:
        """Repeated rust calls accumulate debt."""
        dev = DevelopmentPoints.objects.create(
            character=self.character, trait=self.trait, total_earned=100, rust_debt=10
        )
        result = apply_skill_rust(dev, character_level=5, trait_level=12)
        # 5 + 5 = 10, cap = (12-9)*100 = 300, so 10 applies
        assert result == 10
        dev.refresh_from_db()
        assert dev.rust_debt == 20


class ProcessWeeklySkillDevelopmentTest(TestCase):
    """Test the weekly processing function."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = ObjectDB.objects.create(db_key="WeeklyProcessChar")
        cls.trait_used = TraitFactory(name="weekly_used_trait")
        cls.trait_unused = TraitFactory(name="weekly_unused_trait")
        cls.char_class = CharacterClassFactory(name="weekly_test_class")

    def setUp(self) -> None:
        DevelopmentPoints.flush_instance_cache()
        WeeklySkillUsage.flush_instance_cache()
        CharacterTraitValue.flush_instance_cache()
        DevelopmentTransaction.flush_instance_cache()
        DevelopmentPoints.objects.filter(character=self.character).delete()
        WeeklySkillUsage.objects.filter(character=self.character).delete()
        CharacterTraitValue.objects.filter(character=self.character).delete()
        DevelopmentTransaction.objects.filter(character=self.character).delete()

    def _set_class_level(self, level: int) -> None:
        """Set the character's primary class level."""
        from world.classes.models import CharacterClassLevel

        CharacterClassLevel.objects.update_or_create(
            character=self.character,
            character_class=self.char_class,
            defaults={"level": level, "is_primary": True},
        )

    def test_creates_audit_transactions_for_used_skills(self) -> None:
        """Processed WeeklySkillUsage rows produce DevelopmentTransaction audit records."""
        week = datetime.date(2026, 3, 16)  # a Monday
        WeeklySkillUsage.objects.create(
            character=self.character,
            trait=self.trait_used,
            week_start=week,
            points_earned=50,
            check_count=5,
        )

        process_weekly_skill_development(week)

        txns = DevelopmentTransaction.objects.filter(
            character=self.character, trait=self.trait_used
        )
        assert txns.count() == 1
        txn = txns.first()
        assert txn.amount == 50
        assert txn.source == DevelopmentSource.SCENE
        assert "50 dp" in txn.description
        assert "5 skill checks" in txn.description

    def test_marks_usage_as_processed(self) -> None:
        week = datetime.date(2026, 3, 16)
        WeeklySkillUsage.objects.create(
            character=self.character,
            trait=self.trait_used,
            week_start=week,
            points_earned=20,
            check_count=2,
        )

        process_weekly_skill_development(week)

        # Bypass SharedMemoryModel cache
        usage_data = (
            WeeklySkillUsage.objects.filter(
                character=self.character, trait=self.trait_used, week_start=week
            )
            .values("processed")
            .first()
        )
        assert usage_data is not None
        assert usage_data["processed"] is True

    def test_applies_rust_to_unused_skills(self) -> None:
        """Skills with DevelopmentPoints but no WeeklySkillUsage get rust."""
        self._set_class_level(5)
        week = datetime.date(2026, 3, 16)

        # Unused skill at level 12
        DevelopmentPoints.objects.create(
            character=self.character, trait=self.trait_unused, total_earned=300
        )
        CharacterTraitValue.objects.create(
            character=self.character, trait=self.trait_unused, value=12
        )

        process_weekly_skill_development(week)

        dev = (
            DevelopmentPoints.objects.filter(character=self.character, trait=self.trait_unused)
            .values("rust_debt")
            .first()
        )
        # char_level=5, rust = 5+5 = 10, cap = (12-9)*100 = 300
        assert dev["rust_debt"] == 10

    def test_rust_creates_audit_transaction(self) -> None:
        """Rust application creates a DevelopmentTransaction with source=RUST."""
        self._set_class_level(5)
        week = datetime.date(2026, 3, 16)

        DevelopmentPoints.objects.create(
            character=self.character, trait=self.trait_unused, total_earned=300
        )
        CharacterTraitValue.objects.create(
            character=self.character, trait=self.trait_unused, value=12
        )

        process_weekly_skill_development(week)

        txns = DevelopmentTransaction.objects.filter(
            character=self.character,
            trait=self.trait_unused,
            source=DevelopmentSource.RUST,
        )
        assert txns.count() == 1
        txn = txns.first()
        assert txn.amount == 10
        assert "rust" in txn.description.lower()

    def test_used_skills_dont_get_rust(self) -> None:
        """Skills with WeeklySkillUsage rows are protected from rust."""
        self._set_class_level(5)
        week = datetime.date(2026, 3, 16)

        DevelopmentPoints.objects.create(
            character=self.character, trait=self.trait_used, total_earned=300
        )
        CharacterTraitValue.objects.create(
            character=self.character, trait=self.trait_used, value=12
        )
        WeeklySkillUsage.objects.create(
            character=self.character,
            trait=self.trait_used,
            week_start=week,
            points_earned=10,
            check_count=1,
        )

        process_weekly_skill_development(week)

        dev = (
            DevelopmentPoints.objects.filter(character=self.character, trait=self.trait_used)
            .values("rust_debt")
            .first()
        )
        assert dev["rust_debt"] == 0

    def test_no_rust_for_low_level_skills(self) -> None:
        """Skills at or below level 10 don't get rust even if unused."""
        self._set_class_level(5)
        week = datetime.date(2026, 3, 16)

        DevelopmentPoints.objects.create(
            character=self.character, trait=self.trait_unused, total_earned=50
        )
        CharacterTraitValue.objects.create(
            character=self.character, trait=self.trait_unused, value=10
        )

        process_weekly_skill_development(week)

        dev = (
            DevelopmentPoints.objects.filter(character=self.character, trait=self.trait_unused)
            .values("rust_debt")
            .first()
        )
        assert dev["rust_debt"] == 0

    def test_already_processed_not_reprocessed(self) -> None:
        """Usage rows already marked processed are skipped."""
        week = datetime.date(2026, 3, 16)
        WeeklySkillUsage.objects.create(
            character=self.character,
            trait=self.trait_used,
            week_start=week,
            points_earned=50,
            check_count=5,
            processed=True,
        )

        process_weekly_skill_development(week)

        # No new transactions should be created
        txns = DevelopmentTransaction.objects.filter(character=self.character)
        assert txns.count() == 0
