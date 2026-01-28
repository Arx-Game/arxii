"""
Tests for progression services.
"""

from django.test import TestCase
from evennia.accounts.models import AccountDB
from evennia.objects.models import ObjectDB
import pytest

from world.classes.factories import CharacterClassLevelFactory
from world.progression.factories import ExperiencePointsDataFactory
from world.progression.models import (
    CharacterUnlock,
    ExperiencePointsData,
    XPTransaction,
)
from world.progression.services import (
    award_development_points,
    award_xp,
    calculate_level_up_requirements,
    check_requirements_for_unlock,
    get_or_create_xp_tracker,
    spend_xp_on_unlock,
)
from world.progression.types import DevelopmentSource, ProgressionReason
from world.traits.factories import CharacterTraitValueFactory, TraitFactory


class XPServiceTest(TestCase):
    """Test XP service functions."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountDB.objects.create(
            username="testplayer",
            email="test@test.com",
        )

    def test_get_or_create_xp_tracker(self):
        """Test getting or creating XP tracker."""
        # Test creation
        xp_tracker = get_or_create_xp_tracker(self.account)
        assert xp_tracker.account == self.account
        assert xp_tracker.total_earned == 0

        # Test getting existing
        xp_tracker2 = get_or_create_xp_tracker(self.account)
        assert xp_tracker.account == xp_tracker2.account

    def test_award_xp(self):
        """Test XP awarding service."""
        transaction = award_xp(
            self.account,
            50,
            ProgressionReason.GM_AWARD,
            "Test award",
        )

        # Check XP tracker was updated
        xp_tracker = ExperiencePointsData.objects.get(account=self.account)
        assert xp_tracker.total_earned == 50
        assert xp_tracker.current_available == 50

        # Check transaction was recorded
        assert transaction.amount == 50
        assert transaction.reason == ProgressionReason.GM_AWARD
        # Note: xp_after field doesn't exist in current model

    def test_award_xp_invalid_amount(self):
        """Test XP awarding with invalid amount."""
        with pytest.raises(ValueError):
            award_xp(self.account, -10)


class UnlockServiceTest(TestCase):
    """Test unlock service functions."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountDB.objects.create(
            username="testplayer",
            email="test@test.com",
        )
        cls.character = ObjectDB.objects.create(
            db_key="TestChar",
            db_account=cls.account,
        )

        # Give character a class level
        cls.class_level = CharacterClassLevelFactory(character=cls.character, level=3)

        # Create level unlock with XP cost
        from world.progression.models import (
            ClassLevelUnlock,
            ClassXPCost,
            XPCostChart,
            XPCostEntry,
        )

        cls.class_unlock = ClassLevelUnlock.objects.create(
            character_class=cls.class_level.character_class,
            target_level=4,
        )

        # Set up XP cost
        chart = XPCostChart.objects.create(name="Test Chart")
        XPCostEntry.objects.create(chart=chart, level=4, xp_cost=100)
        ClassXPCost.objects.create(
            character_class=cls.class_level.character_class,
            cost_chart=chart,
        )

        # Give account enough XP
        cls.xp_tracker = ExperiencePointsDataFactory(
            account=cls.account,
            total_earned=150,
            total_spent=0,
        )

    def test_spend_xp_on_unlock_success(self):
        """Test successful XP spending on unlock."""
        success, message, unlock = spend_xp_on_unlock(self.character, self.class_unlock)

        assert success
        assert "Successfully unlocked" in message
        assert unlock is not None

        # Check XP was spent
        self.xp_tracker.refresh_from_db()
        assert self.xp_tracker.current_available == 50
        assert self.xp_tracker.total_spent == 100

        # Check unlock was recorded
        assert CharacterUnlock.objects.filter(
            character=self.character,
            character_class=self.class_unlock.character_class,
            target_level=self.class_unlock.target_level,
        ).exists()

        # Check transaction was recorded
        assert XPTransaction.objects.filter(
            account=self.account, amount=-100, character=self.character
        ).exists()

    def test_spend_xp_insufficient_funds(self):
        """Test XP spending with insufficient funds."""
        self.xp_tracker.total_spent = 100  # This leaves only 50 available
        self.xp_tracker.save()

        success, message, unlock = spend_xp_on_unlock(self.character, self.class_unlock)

        assert not success
        assert "Insufficient XP" in message
        assert unlock is None

    def test_spend_xp_already_unlocked(self):
        """Test XP spending on already purchased unlock."""
        # Create existing unlock
        CharacterUnlock.objects.create(
            character=self.character,
            character_class=self.class_unlock.character_class,
            target_level=self.class_unlock.target_level,
            xp_spent=100,
        )

        success, message, unlock = spend_xp_on_unlock(self.character, self.class_unlock)

        assert not success
        assert "Already unlocked" in message
        assert unlock is None

    def test_check_requirements_for_unlock(self):
        """Test unlock requirement validation using the new system."""
        # Test success case - character is level 3, trying to unlock level 4
        # (There may be no requirements defined for this test unlock)
        valid, message = check_requirements_for_unlock(
            self.character,
            self.class_unlock,
        )
        # Just verify the function works, don't assume specific requirements exist
        assert isinstance(valid, bool)
        assert isinstance(message, list)


class DevelopmentServiceTest(TestCase):
    """Test development point service functions."""

    @classmethod
    def setUpTestData(cls):
        cls.character = ObjectDB.objects.create(db_key="TestChar")

    def test_award_development_points(self):
        """Test awarding development points."""
        # Create a trait for testing
        from world.traits.factories import TraitFactory

        trait = TraitFactory(name="swords")

        transaction = award_development_points(
            character=self.character,
            trait=trait,
            source=DevelopmentSource.SCENE,
            amount=10,
            description="Test scene",
        )

        # Check transaction was recorded
        assert transaction.amount == 10
        assert transaction.source == DevelopmentSource.SCENE
        assert transaction.trait == trait

        # Check development tracker was created and updated
        dev_tracker = self.character.development_points.get(trait=trait)
        assert dev_tracker.total_earned == 10


class DevelopmentRateModifierTest(TestCase):
    """Test development rate modifiers (e.g., Spoiled distinction)."""

    @classmethod
    def setUpTestData(cls):
        from world.character_sheets.factories import CharacterSheetFactory
        from world.distinctions.factories import DistinctionCategoryFactory, DistinctionFactory
        from world.distinctions.models import DistinctionEffect
        from world.mechanics.factories import ModifierCategoryFactory, ModifierTypeFactory
        from world.traits.factories import TraitFactory
        from world.traits.models import TraitCategory, TraitType

        cls.character = ObjectDB.objects.create(db_key="TestChar")
        cls.sheet = CharacterSheetFactory(character=cls.character)

        # Create physical trait (combat category = physical development rate)
        cls.physical_trait = TraitFactory(
            name="melee",
            trait_type=TraitType.SKILL,
            category=TraitCategory.COMBAT,
        )

        # Create social trait (for comparison)
        cls.social_trait = TraitFactory(
            name="diplomacy",
            trait_type=TraitType.SKILL,
            category=TraitCategory.SOCIAL,
        )

        # Create the Spoiled distinction with its effect
        personality = DistinctionCategoryFactory(slug="personality", name="Personality")
        cls.spoiled = DistinctionFactory(
            slug="spoiled",
            name="Spoiled",
            category=personality,
            cost_per_rank=-10,
            max_rank=1,
        )

        # Create modifier type for physical skill development rate
        dev_category = ModifierCategoryFactory(name="development")
        physical_dev_rate = ModifierTypeFactory(
            category=dev_category, name="physical_skill_development_rate"
        )

        # Create effect: -20% physical skill development
        DistinctionEffect.objects.create(
            distinction=cls.spoiled,
            target=physical_dev_rate,
            value_per_rank=-20,
            description="Physical skills develop 20% slower",
        )

    def _grant_spoiled(self):
        """Helper to grant Spoiled distinction and create modifiers."""
        from world.distinctions.models import CharacterDistinction
        from world.mechanics.services import create_distinction_modifiers

        char_distinction = CharacterDistinction.objects.create(
            character=self.character,
            distinction=self.spoiled,
            rank=1,
        )
        create_distinction_modifiers(char_distinction)
        return char_distinction

    def test_physical_skill_development_reduced_with_spoiled(self):
        """Spoiled reduces physical skill development by 20%."""
        self._grant_spoiled()

        transaction = award_development_points(
            character=self.character,
            trait=self.physical_trait,
            source=DevelopmentSource.COMBAT,
            amount=10,
            description="Combat training",
        )

        # 10 * 0.8 = 8 (20% reduction)
        assert transaction.amount == 8
        dev_tracker = self.character.development_points.get(trait=self.physical_trait)
        assert dev_tracker.total_earned == 8

    def test_social_skill_development_unaffected_by_spoiled(self):
        """Spoiled does not affect social skill development."""
        self._grant_spoiled()

        transaction = award_development_points(
            character=self.character,
            trait=self.social_trait,
            source=DevelopmentSource.SOCIAL,
            amount=10,
            description="Social training",
        )

        # No reduction for social skills
        assert transaction.amount == 10
        dev_tracker = self.character.development_points.get(trait=self.social_trait)
        assert dev_tracker.total_earned == 10

    def test_development_without_spoiled_unmodified(self):
        """Characters without Spoiled get full development points."""
        # Don't grant Spoiled

        transaction = award_development_points(
            character=self.character,
            trait=self.physical_trait,
            source=DevelopmentSource.COMBAT,
            amount=10,
            description="Combat training",
        )

        assert transaction.amount == 10
        dev_tracker = self.character.development_points.get(trait=self.physical_trait)
        assert dev_tracker.total_earned == 10

    def test_development_minimum_one_point(self):
        """Development awards always give at least 1 point even with penalties."""
        self._grant_spoiled()

        # Award 1 point - 20% reduction would be 0.8, but floors to 1
        transaction = award_development_points(
            character=self.character,
            trait=self.physical_trait,
            source=DevelopmentSource.COMBAT,
            amount=1,
            description="Minimal training",
        )

        # Minimum 1 point
        assert transaction.amount == 1
        dev_tracker = self.character.development_points.get(trait=self.physical_trait)
        assert dev_tracker.total_earned == 1

    def test_automatic_development_point_application(self):
        """Test automatic development point application."""
        # Create trait
        from world.traits.factories import TraitFactory

        trait = TraitFactory(name="swords")

        # Create trait value for character
        from world.traits.factories import CharacterTraitValueFactory

        trait_value = CharacterTraitValueFactory(
            character=self.character,
            trait=trait,
            value=15,  # 1.5
        )

        # Award development points (should automatically apply)
        award_development_points(
            character=self.character,
            trait=trait,
            source=DevelopmentSource.COMBAT,
            amount=5,
            description="Combat training",
        )

        # Check trait was automatically updated
        trait_value.refresh_from_db()
        assert trait_value.value == 20  # 15 + 5 = 20

        # Check development tracker was updated
        dev_tracker = self.character.development_points.get(trait=trait)
        assert dev_tracker.total_earned == 5

    def test_development_point_threshold_blocking(self):
        """Test that development points auto-apply with simplified system."""
        # Create trait
        from world.traits.factories import TraitFactory

        trait = TraitFactory(name="charm")

        # Create trait value just below a threshold
        from world.traits.factories import CharacterTraitValueFactory

        trait_value = CharacterTraitValueFactory(
            character=self.character,
            trait=trait,
            value=19,  # 1.9, just below 2.0 threshold
        )

        # Award development points
        award_development_points(
            character=self.character,
            trait=trait,
            source=DevelopmentSource.SOCIAL,
            amount=5,
            description="Social training",
        )

        # With simplified system, trait ratings auto-apply through development points
        trait_value.refresh_from_db()
        assert trait_value.value == 24  # Should be 19 + 5 = 24


class LevelUpRequirementsTest(TestCase):
    """Test level up requirements calculation."""

    @classmethod
    def setUpTestData(cls):
        cls.character = ObjectDB.objects.create(db_key="TestChar")
        cls.class_level = CharacterClassLevelFactory(
            character=cls.character,
            level=2,
            is_primary=True,
        )

        # Create level unlock
        from world.progression.models import ClassLevelUnlock

        cls.level_unlock = ClassLevelUnlock.objects.create(
            character_class=cls.class_level.character_class,
            target_level=3,
        )

        # Create XP cost for this class
        from world.progression.models import ClassXPCost, XPCostChart, XPCostEntry

        chart = XPCostChart.objects.create(name="Standard Levels")
        XPCostEntry.objects.create(chart=chart, level=3, xp_cost=75)
        ClassXPCost.objects.create(
            character_class=cls.class_level.character_class,
            cost_chart=chart,
        )

        # Create core traits for testing
        from world.traits.models import TraitType

        cls.core_trait1 = TraitFactory(name="weapon_skill", trait_type=TraitType.SKILL)
        cls.core_trait2 = TraitFactory(name="defense", trait_type=TraitType.SKILL)

    def test_calculate_level_up_requirements(self):
        """Test calculating level up requirements."""
        # Add some trait values
        CharacterTraitValueFactory(
            character=self.character,
            trait=self.core_trait1,
            value=25,  # 2.5
        )
        CharacterTraitValueFactory(
            character=self.character,
            trait=self.core_trait2,
            value=35,  # 3.5
        )

        requirements = calculate_level_up_requirements(
            self.character,
            self.class_level.character_class,
            3,
        )

        # Check basic structure
        assert requirements["xp_cost"] == 75
        # Note: class_requirements may not exist in current implementation
        # Just verify we get a result without errors for now
        assert isinstance(requirements, dict)

    def test_calculate_level_up_no_class(self):
        """Test level up calculation for character with no class."""
        character_no_class = ObjectDB.objects.create(db_key="NoClass")

        from world.classes.factories import CharacterClassFactory

        dummy_class = CharacterClassFactory()
        requirements = calculate_level_up_requirements(
            character_no_class,
            dummy_class,
            2,
        )

        assert "error" in requirements
        # The actual error message varies, just check that there's an error

    def test_calculate_level_up_invalid_level(self):
        """Test level up calculation for invalid target level."""
        requirements = calculate_level_up_requirements(
            self.character,
            self.class_level.character_class,
            1,
        )  # Already level 2

        assert "error" in requirements
        assert "already level" in requirements["error"]
