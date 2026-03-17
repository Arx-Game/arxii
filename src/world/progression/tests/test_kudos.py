"""
Tests for kudos models and services.
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
    ExperiencePointsData,
    KudosClaimCategory,
    KudosPointsData,
    KudosSourceCategory,
    KudosTransaction,
)
from world.progression.services import (
    InsufficientKudosError,
    award_kudos,
    claim_kudos,
    claim_kudos_for_xp,
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

    def setUp(self):
        # Flush SharedMemoryModel caches to prevent test pollution
        KudosPointsData.flush_instance_cache()

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


class KudosServiceTest(TestCase):
    """Test kudos service functions."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountDB.objects.create(
            username="testplayer",
            email="test@test.com",
        )
        cls.awarder = AccountDB.objects.create(
            username="awarder",
            email="awarder@test.com",
        )
        cls.source_category = KudosSourceCategoryFactory(name="player_vote")
        cls.claim_category = KudosClaimCategoryFactory(name="xp", kudos_cost=10, reward_amount=5)

    def setUp(self):
        # Flush SharedMemoryModel caches and clean up per-test state
        KudosPointsData.flush_instance_cache()
        KudosTransaction.flush_instance_cache()
        # Delete any KudosPointsData created by previous tests for this account
        KudosPointsData.objects.filter(account=self.account).delete()
        KudosTransaction.objects.filter(account=self.account).delete()

    def test_award_kudos_creates_points_data(self):
        """Test awarding kudos creates KudosPointsData if it doesn't exist."""
        result = award_kudos(
            account=self.account,
            amount=25,
            source_category=self.source_category,
            description="Thanks for helping!",
        )

        assert result.points_data.total_earned == 25
        assert result.points_data.current_available == 25
        assert result.transaction.amount == 25
        assert result.transaction.source_category == self.source_category

    def test_award_kudos_updates_existing_points(self):
        """Test awarding kudos to an account that already has kudos."""
        # First award
        award_kudos(
            account=self.account,
            amount=10,
            source_category=self.source_category,
            description="First award",
        )

        # Second award
        result = award_kudos(
            account=self.account,
            amount=15,
            source_category=self.source_category,
            description="Second award",
        )

        assert result.points_data.total_earned == 25
        assert result.points_data.current_available == 25

    def test_award_kudos_with_awarded_by(self):
        """Test awarding kudos with an awarder specified."""
        result = award_kudos(
            account=self.account,
            amount=5,
            source_category=self.source_category,
            description="Player vote",
            awarded_by=self.awarder,
        )

        assert result.transaction.awarded_by == self.awarder

    def test_award_kudos_rejects_non_positive_amount(self):
        """Test that awarding zero or negative kudos raises ValueError."""
        with pytest.raises(ValueError, match="must be positive"):
            award_kudos(
                account=self.account,
                amount=0,
                source_category=self.source_category,
                description="Invalid",
            )

        with pytest.raises(ValueError, match="must be positive"):
            award_kudos(
                account=self.account,
                amount=-5,
                source_category=self.source_category,
                description="Invalid",
            )

    def test_claim_kudos_success(self):
        """Test successfully claiming kudos."""
        # First award some kudos
        award_kudos(
            account=self.account,
            amount=100,
            source_category=self.source_category,
            description="Award",
        )

        # Now claim some
        result = claim_kudos(
            account=self.account,
            amount=50,
            claim_category=self.claim_category,
            description="Converting to XP",
        )

        assert result.points_data.total_claimed == 50
        assert result.points_data.current_available == 50
        assert result.transaction.amount == -50  # Negative for claims
        assert result.transaction.claim_category == self.claim_category
        assert result.reward_amount == 25  # 50 kudos at 10:5 ratio = 25 reward

    def test_claim_kudos_insufficient_balance(self):
        """Test claiming more kudos than available raises error."""
        # Award some kudos
        award_kudos(
            account=self.account,
            amount=30,
            source_category=self.source_category,
            description="Award",
        )

        # Try to claim more than available
        with pytest.raises(InsufficientKudosError, match="Insufficient kudos"):
            claim_kudos(
                account=self.account,
                amount=50,
                claim_category=self.claim_category,
                description="Too much",
            )

    def test_claim_kudos_rejects_non_positive_amount(self):
        """Test that claiming zero or negative kudos raises ValueError."""
        with pytest.raises(ValueError, match="must be positive"):
            claim_kudos(
                account=self.account,
                amount=0,
                claim_category=self.claim_category,
                description="Invalid",
            )

    def test_service_creates_transaction_records(self):
        """Test that service functions create proper transaction records."""
        award_kudos(
            account=self.account,
            amount=50,
            source_category=self.source_category,
            description="Award",
        )
        claim_kudos(
            account=self.account,
            amount=20,
            claim_category=self.claim_category,
            description="Claim",
        )

        transactions = KudosTransaction.objects.filter(account=self.account)
        assert transactions.count() == 2

        award_tx = transactions.get(amount__gt=0)
        assert award_tx.source_category == self.source_category

        claim_tx = transactions.get(amount__lt=0)
        assert claim_tx.claim_category == self.claim_category


class ClaimKudosForXPTest(TestCase):
    """Test claim_kudos_for_xp orchestration."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountDB.objects.create(
            username="testplayer",
            email="test@test.com",
        )
        cls.source_category = KudosSourceCategoryFactory(name="test_source")
        cls.claim_category = KudosClaimCategoryFactory(
            name="xp_convert", kudos_cost=1, reward_amount=1
        )

    def setUp(self):
        # Flush SharedMemoryModel caches and clean up per-test state
        KudosPointsData.flush_instance_cache()
        KudosTransaction.flush_instance_cache()
        ExperiencePointsData.flush_instance_cache()
        KudosPointsData.objects.filter(account=self.account).delete()
        KudosTransaction.objects.filter(account=self.account).delete()
        ExperiencePointsData.objects.filter(account=self.account).delete()

    def _seed_kudos(self, amount: int) -> None:
        award_kudos(
            account=self.account,
            amount=amount,
            source_category=self.source_category,
            description="Seed kudos",
        )

    def test_claims_kudos_and_awards_xp(self):
        """Claiming kudos for XP deducts kudos and awards XP atomically."""
        self._seed_kudos(50)
        result = claim_kudos_for_xp(
            account=self.account,
            amount=50,
            claim_category=self.claim_category,
        )
        assert result.xp_awarded == 50
        assert result.claim_result.points_data.current_available == 0
        xp_data = ExperiencePointsData.objects.get(account=self.account)
        assert xp_data.current_available == 50

    def test_xp_transaction_created_with_kudos_reason(self):
        """XP transaction uses KUDOS_CLAIM reason."""
        self._seed_kudos(10)
        result = claim_kudos_for_xp(
            account=self.account,
            amount=10,
            claim_category=self.claim_category,
        )
        assert result.xp_transaction.reason == "kudos_claim"

    def test_respects_conversion_rate(self):
        """Non-1:1 conversion rate awards correct XP."""
        category = KudosClaimCategoryFactory(name="xp_2to1", kudos_cost=2, reward_amount=1)
        self._seed_kudos(10)
        result = claim_kudos_for_xp(
            account=self.account,
            amount=10,
            claim_category=category,
        )
        assert result.xp_awarded == 5

    def test_insufficient_kudos_raises(self):
        """Raises InsufficientKudosError when balance too low."""
        self._seed_kudos(5)
        with pytest.raises(InsufficientKudosError):
            claim_kudos_for_xp(
                account=self.account,
                amount=10,
                claim_category=self.claim_category,
            )

    def test_zero_reward_raises(self):
        """Raises ValueError when kudos amount yields zero XP."""
        category = KudosClaimCategoryFactory(name="expensive", kudos_cost=100, reward_amount=1)
        self._seed_kudos(50)
        with pytest.raises(ValueError, match="not enough for any XP"):
            claim_kudos_for_xp(
                account=self.account,
                amount=50,
                claim_category=category,
            )

    def test_atomic_rollback_on_failure(self):
        """If XP award fails, kudos claim is rolled back."""
        self._seed_kudos(10)
        # Zero-reward triggers ValueError after kudos are claimed —
        # the atomic transaction should roll back the claim too
        category = KudosClaimCategoryFactory(name="zero_reward", kudos_cost=100, reward_amount=1)
        with pytest.raises(ValueError):
            claim_kudos_for_xp(
                account=self.account,
                amount=10,
                claim_category=category,
            )
        # Kudos should NOT have been deducted
        # Flush identity mapper cache so .get() re-reads from DB after rollback
        KudosPointsData.flush_instance_cache()
        points = KudosPointsData.objects.get(account=self.account)
        assert points.current_available == 10

    def test_default_description_generated(self):
        """Auto-generates description when none provided."""
        self._seed_kudos(10)
        result = claim_kudos_for_xp(
            account=self.account,
            amount=10,
            claim_category=self.claim_category,
        )
        assert "Claimed 10 kudos" in result.claim_result.transaction.description
        assert "Converted 10 kudos to 10 XP" in result.xp_transaction.description
