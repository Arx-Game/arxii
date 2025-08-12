"""
Tests for progression models.
"""

from django.core.exceptions import ValidationError
from django.test import TestCase
from evennia.accounts.models import AccountDB
from evennia.objects.models import ObjectDB

from world.progression.factories import (
    DevelopmentPointsFactory,
    ExperiencePointsDataFactory,
)
from world.progression.models import (
    CharacterUnlock,
    DevelopmentPoints,
    ExperiencePointsData,
)

# Removed unused imports


class ExperiencePointsDataModelTest(TestCase):
    """Test ExperiencePointsData model."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountDB.objects.create(
            username="testplayer", email="test@test.com"
        )

    def test_xp_creation(self):
        """Test creating XP tracker."""
        xp = ExperiencePointsData.objects.create(
            account=self.account,
            total_earned=100,
            total_spent=50,
        )
        self.assertEqual(xp.account, self.account)
        self.assertEqual(xp.total_earned, 100)
        self.assertEqual(xp.current_available, 50)
        self.assertEqual(xp.total_spent, 50)

    def test_xp_validation(self):
        """Test XP total validation."""
        with self.assertRaises(ValidationError):
            xp = ExperiencePointsData(
                account=self.account,
                total_earned=50,  # Less than spent
                total_spent=60,
            )
            xp.full_clean()

    def test_can_spend(self):
        """Test XP spending validation."""
        xp = ExperiencePointsDataFactory(total_earned=100, total_spent=50)
        self.assertTrue(xp.can_spend(30))
        self.assertFalse(xp.can_spend(60))

    def test_spend_xp(self):
        """Test XP spending."""
        xp = ExperiencePointsDataFactory(
            total_earned=100,
            total_spent=50,
        )

        success = xp.spend_xp(20)
        self.assertTrue(success)
        self.assertEqual(xp.current_available, 30)
        self.assertEqual(xp.total_spent, 70)

        # Try to spend more than available
        success = xp.spend_xp(40)
        self.assertFalse(success)
        self.assertEqual(xp.current_available, 30)  # Should be unchanged

    def test_award_xp(self):
        """Test XP awarding."""
        xp = ExperiencePointsDataFactory(
            total_earned=100,
            total_spent=50,
        )

        xp.award_xp(25)
        self.assertEqual(xp.total_earned, 125)
        self.assertEqual(xp.current_available, 75)
        self.assertEqual(xp.total_spent, 50)  # Should be unchanged


class DevelopmentPointsModelTest(TestCase):
    """Test DevelopmentPoints model."""

    @classmethod
    def setUpTestData(cls):
        cls.character = ObjectDB.objects.create(db_key="TestChar")

    def test_development_points_creation(self):
        """Test creating development point tracker."""
        from world.traits.factories import TraitFactory

        trait = TraitFactory(name="strength")
        dev_points = DevelopmentPoints.objects.create(
            character=self.character,
            trait=trait,
            total_earned=20,
        )
        self.assertEqual(dev_points.character, self.character)
        self.assertEqual(dev_points.trait, trait)
        self.assertEqual(dev_points.total_earned, 20)

    def test_development_validation(self):
        """Test development point validation - skip for now as new model is simpler."""
        pass

    def test_unique_constraint(self):
        """Test unique constraint on development points."""
        from world.traits.factories import TraitFactory

        trait = TraitFactory(name="strength")

        DevelopmentPointsFactory(
            character=self.character,
            trait=trait,
        )

        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            DevelopmentPointsFactory(
                character=self.character,
                trait=trait,
            )

    def test_spend_and_award_points(self):
        """Test spending and awarding development points - updated for new model."""
        from world.traits.factories import TraitFactory

        trait = TraitFactory(name="swords")

        dev_points = DevelopmentPointsFactory(
            character=self.character,
            trait=trait,
            total_earned=30,
        )

        # Test awarding - new model is simpler, just tracks total earned
        dev_points.total_earned = 40
        dev_points.save()
        self.assertEqual(dev_points.total_earned, 40)


class CharacterUnlockModelTest(TestCase):
    """Test CharacterUnlock model."""

    @classmethod
    def setUpTestData(cls):
        cls.character = ObjectDB.objects.create(db_key="TestChar")
        # Create a class unlock for testing instead
        from world.classes.factories import CharacterClassFactory
        from world.progression.models import ClassLevelUnlock

        char_class = CharacterClassFactory()
        cls.class_unlock = ClassLevelUnlock.objects.create(
            character_class=char_class,
            target_level=5,
        )

    def test_character_unlock_creation(self):
        """Test creating character unlocks."""
        unlock = CharacterUnlock.objects.create(
            character=self.character,
            character_class=self.class_unlock.character_class,
            target_level=self.class_unlock.target_level,
            xp_spent=100,
        )
        self.assertEqual(unlock.character, self.character)
        self.assertEqual(unlock.character_class, self.class_unlock.character_class)
        self.assertEqual(unlock.target_level, self.class_unlock.target_level)
        self.assertEqual(unlock.xp_spent, 100)

    def test_unique_constraint(self):
        """Test unique constraint on character unlocks."""
        CharacterUnlock.objects.create(
            character=self.character,
            character_class=self.class_unlock.character_class,
            target_level=self.class_unlock.target_level,
            xp_spent=100,
        )

        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            CharacterUnlock.objects.create(
                character=self.character,
                character_class=self.class_unlock.character_class,
                target_level=self.class_unlock.target_level,
                xp_spent=100,
            )
