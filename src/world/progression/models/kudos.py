"""
Kudos models for the progression system.

Kudos is a "good sport" currency that rewards positive community behavior:
- Player votes for helpfulness
- Graceful character deaths
- Mentoring new players
- Covering for GMs
- Defusing OOC conflicts

Kudos can be claimed/converted to XP or CG points.
"""

from typing import ClassVar, cast

from django.core.exceptions import ValidationError
from django.db import models
from evennia.accounts.models import AccountDB
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin


class KudosSourceCategory(NaturalKeyMixin, SharedMemoryModel):
    """
    Configurable categories for kudos sources.

    Staff can add new categories as they think of new ways to award kudos.
    Examples: Player Vote, Staff Award, Graceful Death, Mentoring, etc.
    """

    name = models.CharField(
        max_length=50,
        unique=True,
        help_text="Internal name (e.g., 'player_vote', 'death_bonus')",
    )
    display_name = models.CharField(
        max_length=100,
        help_text="Human-readable name (e.g., 'Player Vote', 'Graceful Character Death')",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of what this category rewards",
    )
    default_amount = models.PositiveIntegerField(
        default=1,
        help_text="Default kudos amount for this category",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this category is currently available",
    )
    # Some categories require staff to award (vs player votes)
    staff_only = models.BooleanField(
        default=False,
        help_text="If true, only staff can award this type of kudos",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    def __str__(self):
        return self.display_name

    class Meta:
        verbose_name = "Kudos Source Category"
        verbose_name_plural = "Kudos Source Categories"


class KudosClaimCategory(NaturalKeyMixin, SharedMemoryModel):
    """
    Configurable categories for kudos claims/conversions.

    Staff can define what kudos can be converted to and at what rates.
    Examples: Convert to XP, Convert to CG Points, etc.
    """

    name = models.CharField(
        max_length=50,
        unique=True,
        help_text="Internal name (e.g., 'xp', 'cg_points')",
    )
    display_name = models.CharField(
        max_length=100,
        help_text="Human-readable name (e.g., 'Convert to XP')",
    )
    description = models.TextField(
        blank=True,
        help_text="Description shown to players explaining this claim option",
    )
    kudos_cost = models.PositiveIntegerField(
        help_text="How many kudos required for one unit of reward",
    )
    reward_amount = models.PositiveIntegerField(
        help_text="How much reward is granted per kudos_cost spent",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this claim type is currently available",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    def __str__(self):
        return f"{self.display_name}: {self.kudos_cost} kudos = {self.reward_amount}"

    def calculate_reward(self, kudos_amount: int) -> int:
        """Calculate how much reward a given kudos amount would yield."""
        if cast(int, self.kudos_cost) == 0:
            return 0
        return (kudos_amount // cast(int, self.kudos_cost)) * cast(int, self.reward_amount)

    def calculate_kudos_needed(self, reward_amount: int) -> int:
        """Calculate how many kudos are needed for a desired reward amount."""
        if cast(int, self.reward_amount) == 0:
            return 0
        units_needed = (reward_amount + cast(int, self.reward_amount) - 1) // cast(
            int, self.reward_amount
        )
        return units_needed * cast(int, self.kudos_cost)

    class Meta:
        verbose_name = "Kudos Claim Category"
        verbose_name_plural = "Kudos Claim Categories"


class KudosPointsData(models.Model):
    """
    Kudos points stored on player accounts.

    Unlike XP which is spent and gone, Kudos is claimed/converted
    to other currencies (XP, CG points) through KudosClaimCategory.
    """

    account = models.OneToOneField(
        AccountDB,
        on_delete=models.CASCADE,
        related_name="kudos_points_data",
        primary_key=True,
        help_text="The account this kudos belongs to",
    )
    total_earned = models.PositiveIntegerField(
        default=0,
        help_text="Total kudos earned over time",
    )
    total_claimed = models.PositiveIntegerField(
        default=0,
        help_text="Total kudos claimed/converted over time",
    )
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

    @property
    def current_available(self) -> int:
        """Kudos currently available to claim (calculated property)."""
        total_earned = cast(int, self.total_earned)
        total_claimed = cast(int, self.total_claimed)
        return total_earned - total_claimed

    def clean(self):
        """Validate kudos totals are consistent."""
        super().clean()
        if cast(int, self.total_claimed) > cast(int, self.total_earned):
            msg = "Total claimed cannot exceed total earned kudos"
            raise ValidationError(msg)

    def can_claim(self, amount: int) -> bool:
        """Check if account has enough kudos to claim the given amount."""
        return self.current_available >= amount

    def claim_kudos(self, amount: int) -> bool:
        """Claim kudos if available, updating totals."""
        if not self.can_claim(amount):
            return False
        self.total_claimed += amount
        self.save()
        return True

    def award_kudos(self, amount: int) -> None:
        """Award kudos to the account."""
        self.total_earned += amount
        self.save()

    def __str__(self):
        return f"{self.account.username}: {self.current_available}/{self.total_earned} Kudos"

    class Meta:
        verbose_name = "Kudos Points Data"
        verbose_name_plural = "Kudos Points Data"


class KudosTransaction(models.Model):
    """
    Audit trail for all kudos transactions.

    Unlike XP transactions, kudos transactions include rich metadata
    to serve as a positive reinforcement feed - players see WHY they
    earned kudos, which feels good and reinforces valued behavior.
    """

    account = models.ForeignKey(
        AccountDB,
        on_delete=models.CASCADE,
        related_name="kudos_transactions",
    )
    amount = models.IntegerField(
        help_text="Kudos change (positive for awards, negative for claims)",
    )
    source_category = models.ForeignKey(
        KudosSourceCategory,
        on_delete=models.PROTECT,
        related_name="transactions",
        null=True,
        blank=True,
        help_text="Source category for awards (null for claims)",
    )
    claim_category = models.ForeignKey(
        KudosClaimCategory,
        on_delete=models.PROTECT,
        related_name="transactions",
        null=True,
        blank=True,
        help_text="Claim category for claims (null for awards)",
    )
    description = models.CharField(
        max_length=500,
        help_text="Visible description explaining why kudos was awarded/claimed",
    )
    # Who awarded it (for player votes, staff awards)
    awarded_by = models.ForeignKey(
        AccountDB,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="kudos_awarded",
        help_text="Account that awarded this kudos (if applicable)",
    )
    # Link to character if relevant (e.g., death bonus)
    character = models.ForeignKey(
        "objects.ObjectDB",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="kudos_transactions",
        help_text="Character involved (e.g., for death bonus)",
    )
    transaction_date = models.DateTimeField(auto_now_add=True)

    def clean(self):
        """Validate that either source_category or claim_category is set, not both."""
        super().clean()
        amount = cast(int, self.amount)
        if amount == 0:
            msg = "Transaction amount cannot be zero"
            raise ValidationError(msg)
        if amount > 0 and not self.source_category:
            msg = "Awards (positive amount) must have a source_category"
            raise ValidationError(msg)
        if amount < 0 and not self.claim_category:
            msg = "Claims (negative amount) must have a claim_category"
            raise ValidationError(msg)
        if self.source_category and self.claim_category:
            msg = "Transaction cannot have both source_category and claim_category"
            raise ValidationError(msg)

    def __str__(self):
        amount_value = cast(int, self.amount)
        sign = "+" if amount_value >= 0 else ""
        category = self.source_category or self.claim_category
        category_name = category.display_name if category else "Unknown"
        return f"{self.account.username}: {sign}{amount_value} Kudos ({category_name})"

    class Meta:
        ordering: ClassVar[list[str]] = ["-transaction_date"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["account", "-transaction_date"]),
            models.Index(fields=["source_category", "-transaction_date"]),
        ]
