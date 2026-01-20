"""
Tests for kudos models.
"""

from django.core.exceptions import ValidationError
from django.test import TestCase
from evennia.accounts.models import AccountDB
import pytest

from world.progression.factories import (
    KudosClaimCategoryFactory,
    KudosPointsDataFactory,
    KudosSourceCategoryFactory,
    KudosTransactionFactory,
)
from world.progression.models import (
    KudosClaimCategory,
    KudosPointsData,
    KudosSourceCategory,
    KudosTransaction,
)


class KudosSourceCategoryModelTest(TestCase):
    """Test KudosSourceCategory model."""

    def test_create_source_category(self):
        """Test creating a kudos source category."""
        category = KudosSourceCategory.objects.create(
            name="player_vote",
            display_name="Player Vote",
            description="Awarded when players vote for helpful behavior",
            default_amount=2,
            is_active=True,
            staff_only=False,
        )
        assert category.name == "player_vote"
        assert category.display_name == "Player Vote"
        assert category.default_amount == 2
        assert str(category) == "Player Vote"

    def test_staff_only_category(self):
        """Test staff-only category flag."""
        category = KudosSourceCategoryFactory(staff_only=True)
        assert category.staff_only is True


class KudosClaimCategoryModelTest(TestCase):
    """Test KudosClaimCategory model."""

    def test_create_claim_category(self):
        """Test creating a kudos claim category."""
        category = KudosClaimCategory.objects.create(
            name="xp",
            display_name="Convert to XP",
            description="Convert kudos points to experience points",
            kudos_cost=10,
            reward_amount=5,
            is_active=True,
        )
        assert category.name == "xp"
        assert category.kudos_cost == 10
        assert category.reward_amount == 5

    def test_calculate_reward(self):
        """Test reward calculation."""
        category = KudosClaimCategoryFactory(kudos_cost=10, reward_amount=5)

        # 10 kudos = 5 reward
        assert category.calculate_reward(10) == 5
        # 25 kudos = 10 reward (only full units)
        assert category.calculate_reward(25) == 10
        # 9 kudos = 0 reward (not enough for 1 unit)
        assert category.calculate_reward(9) == 0

    def test_calculate_kudos_needed(self):
        """Test kudos needed calculation."""
        category = KudosClaimCategoryFactory(kudos_cost=10, reward_amount=5)

        # Need 5 reward = 10 kudos
        assert category.calculate_kudos_needed(5) == 10
        # Need 6 reward = 20 kudos (rounds up to next unit)
        assert category.calculate_kudos_needed(6) == 20


class KudosPointsDataModelTest(TestCase):
    """Test KudosPointsData model."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountDB.objects.create(
            username="testplayer",
            email="test@test.com",
        )

    def test_kudos_creation(self):
        """Test creating kudos tracker."""
        kudos = KudosPointsData.objects.create(
            account=self.account,
            total_earned=100,
            total_claimed=30,
        )
        assert kudos.account == self.account
        assert kudos.total_earned == 100
        assert kudos.total_claimed == 30
        assert kudos.current_available == 70

    def test_kudos_validation(self):
        """Test kudos total validation."""
        with pytest.raises(ValidationError):
            kudos = KudosPointsData(
                account=self.account,
                total_earned=50,
                total_claimed=60,  # More than earned
            )
            kudos.full_clean()

    def test_can_claim(self):
        """Test kudos claim validation."""
        kudos = KudosPointsDataFactory(total_earned=100, total_claimed=30)
        assert kudos.can_claim(50)
        assert not kudos.can_claim(80)

    def test_claim_kudos(self):
        """Test claiming kudos."""
        kudos = KudosPointsDataFactory(total_earned=100, total_claimed=30)

        success = kudos.claim_kudos(20)
        assert success
        assert kudos.current_available == 50
        assert kudos.total_claimed == 50

        # Try to claim more than available
        success = kudos.claim_kudos(60)
        assert not success
        assert kudos.current_available == 50  # Unchanged

    def test_award_kudos(self):
        """Test awarding kudos."""
        kudos = KudosPointsDataFactory(total_earned=100, total_claimed=30)

        kudos.award_kudos(25)
        assert kudos.total_earned == 125
        assert kudos.current_available == 95
        assert kudos.total_claimed == 30  # Unchanged

    def test_str_representation(self):
        """Test string representation."""
        kudos = KudosPointsDataFactory(total_earned=100, total_claimed=30)
        expected = f"{kudos.account.username}: 70/100 Kudos"
        assert str(kudos) == expected


class KudosTransactionModelTest(TestCase):
    """Test KudosTransaction model."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountDB.objects.create(
            username="testplayer",
            email="test@test.com",
        )
        cls.source_category = KudosSourceCategoryFactory(name="player_vote")
        cls.claim_category = KudosClaimCategoryFactory(name="xp")

    def test_create_award_transaction(self):
        """Test creating an award (positive) transaction."""
        transaction = KudosTransaction.objects.create(
            account=self.account,
            amount=5,
            source_category=self.source_category,
            description="Thanks for helping with my scene!",
        )
        assert transaction.amount == 5
        assert transaction.source_category == self.source_category
        assert transaction.claim_category is None

    def test_create_claim_transaction(self):
        """Test creating a claim (negative) transaction."""
        transaction = KudosTransaction.objects.create(
            account=self.account,
            amount=-10,
            claim_category=self.claim_category,
            description="Claimed for XP",
        )
        assert transaction.amount == -10
        assert transaction.source_category is None
        assert transaction.claim_category == self.claim_category

    def test_validation_award_needs_source(self):
        """Test that awards require source_category."""
        with pytest.raises(ValidationError):
            transaction = KudosTransaction(
                account=self.account,
                amount=5,  # Positive = award
                description="Missing source",
            )
            transaction.full_clean()

    def test_validation_claim_needs_claim_category(self):
        """Test that claims require claim_category."""
        with pytest.raises(ValidationError):
            transaction = KudosTransaction(
                account=self.account,
                amount=-10,  # Negative = claim
                description="Missing claim category",
            )
            transaction.full_clean()

    def test_validation_cannot_have_both_categories(self):
        """Test that transaction cannot have both source and claim categories."""
        with pytest.raises(ValidationError):
            transaction = KudosTransaction(
                account=self.account,
                amount=5,
                source_category=self.source_category,
                claim_category=self.claim_category,
                description="Invalid - has both",
            )
            transaction.full_clean()

    def test_validation_zero_amount_rejected(self):
        """Test that zero amount transactions are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            transaction = KudosTransaction(
                account=self.account,
                amount=0,
                source_category=self.source_category,
                description="Invalid - zero amount",
            )
            transaction.full_clean()
        assert "cannot be zero" in str(exc_info.value)

    def test_transaction_with_awarded_by(self):
        """Test transaction with awarded_by field."""
        awarder = AccountDB.objects.create(
            username="awarder",
            email="awarder@test.com",
        )
        transaction = KudosTransactionFactory(
            account=self.account,
            awarded_by=awarder,
            source_category=self.source_category,
        )
        assert transaction.awarded_by == awarder

    def test_str_representation(self):
        """Test string representation."""
        transaction = KudosTransaction.objects.create(
            account=self.account,
            amount=5,
            source_category=self.source_category,
            description="Test",
        )
        expected = f"{self.account.username}: +5 Kudos ({self.source_category.display_name})"
        assert str(transaction) == expected
