"""
Reward models for the progression system.

This module contains models related to earning and tracking rewards:
- ExperiencePointsData: XP storage and management
- XPTransaction: XP transaction audit trail
- DevelopmentPoints: Development point earning and auto-application
- DevelopmentTransaction: Development point transaction audit trail
"""

from typing import ClassVar, cast

from django.core.exceptions import ValidationError
from django.db import models
from evennia.accounts.models import AccountDB
from evennia.utils.idmapper.models import SharedMemoryModel

from world.progression.constants import (
    DP_BASE_LEVEL,
    DP_COST_MULTIPLIER,
)
from world.progression.types import DevelopmentSource, ProgressionReason
from world.traits.models import CharacterTraitValue


def cumulative_dp_for_level(level: int) -> int:
    """Total dp needed to reach *level* from the base level of 10.

    Going from level N to N+1 costs ``(N - 9) * 100`` dp, so:

    * Level 10: 0 dp (CG starting point)
    * Level 11: 100 dp
    * Level 12: 300 dp  (100 + 200)
    * Level 13: 600 dp  (100 + 200 + 300)
    """
    if level <= DP_BASE_LEVEL:
        return 0
    # Closed-form arithmetic series: sum of (1+2+...+steps) * DP_COST_MULTIPLIER
    steps = level - DP_BASE_LEVEL
    return (DP_COST_MULTIPLIER * steps * (steps + 1)) // 2


class ExperiencePointsData(SharedMemoryModel):
    """Experience points stored on player accounts."""

    account = models.OneToOneField(
        AccountDB,
        on_delete=models.CASCADE,
        related_name="experience_points_data",
        primary_key=True,
        help_text="The account this XP belongs to",
    )
    total_earned = models.PositiveIntegerField(
        default=0,
        help_text="Total XP earned over time",
    )
    total_spent = models.PositiveIntegerField(
        default=0,
        help_text="Total XP spent over time",
    )
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

    @property
    def current_available(self) -> int:
        """XP currently available to spend (calculated property)."""
        total_earned = cast(int, self.total_earned)
        total_spent = cast(int, self.total_spent)
        return total_earned - total_spent

    def clean(self) -> None:
        """Validate XP totals are consistent."""
        super().clean()
        if cast(int, self.total_spent) > cast(int, self.total_earned):
            msg = "Total spent cannot exceed total earned XP"
            raise ValidationError(msg)

    def can_spend(self, amount: int) -> bool:
        """Check if account has enough XP to spend the given amount."""
        return self.current_available >= amount

    def spend_xp(self, amount: int) -> bool:
        """Spend XP if available, updating totals."""
        if not self.can_spend(amount):
            return False
        self.total_spent += amount
        self.save()
        return True

    def award_xp(self, amount: int) -> None:
        """Award XP to the account."""
        self.total_earned += amount
        self.save()

    def __str__(self) -> str:
        return f"{self.account.username}: {self.current_available}/{self.total_earned} XP"

    class Meta:
        verbose_name = "Experience Points Data"
        verbose_name_plural = "Experience Points Data"


class XPTransaction(SharedMemoryModel):
    """Audit trail for all XP transactions."""

    account = models.ForeignKey(
        AccountDB,
        on_delete=models.CASCADE,
        related_name="xp_transactions",
    )
    amount = models.IntegerField(
        help_text="XP change (positive for awards, negative for spending)",
    )
    reason = models.CharField(
        max_length=20,
        choices=ProgressionReason.choices,
        help_text="Reason for this transaction",
    )
    description = models.CharField(
        max_length=255,
        blank=True,
        help_text="Detailed description",
    )
    character = models.ForeignKey(
        "objects.ObjectDB",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        help_text="Character this XP was spent on (if applicable)",
    )
    gm = models.ForeignKey(
        AccountDB,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="xp_transactions_created",
        help_text="GM who made this change",
    )
    transaction_date = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        amount_value = cast(int, self.amount)
        sign = "+" if amount_value >= 0 else ""
        return f"{self.account.username}: {sign}{amount_value} XP ({self.get_reason_display()})"

    class Meta:
        ordering: ClassVar[list[str]] = ["-transaction_date"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["account", "-transaction_date"]),
            models.Index(fields=["character", "-transaction_date"]),
        ]


class DevelopmentPoints(SharedMemoryModel):
    """Development points earned by characters through activity."""

    character_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="development_points",
    )
    trait = models.ForeignKey(
        "traits.Trait",
        on_delete=models.CASCADE,
        related_name="development_points",
    )
    total_earned = models.PositiveIntegerField(
        default=0,
        help_text="Total development points earned",
    )
    rust_debt = models.PositiveIntegerField(
        default=0,
        help_text="Rust debt that must be paid off before dp counts toward advancement",
    )
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

    def award_points(self, amount: int) -> list[tuple[int, int]]:
        """Award development points and level up the trait when thresholds are crossed.

        If there is outstanding ``rust_debt``, incoming dp pays off the debt first.
        Only the remainder counts toward the ``total_earned`` accumulator and
        potential level-ups.

        Assumes trait values are on the 1-100 internal scale where DP_BASE_LEVEL (10)
        represents the minimum progression level. Values below 10 will be implicitly
        advanced to 10 on first dp award (cumulative_dp_for_level returns 0 for
        levels <= 10).

        Args:
            amount: Development points to award.

        Returns:
            List of ``(old_level, new_level)`` tuples for each level-up that occurred.
        """
        if self.rust_debt > 0:
            payoff = min(amount, self.rust_debt)
            self.rust_debt -= payoff
            amount -= payoff

        self.total_earned += amount
        self.save()

        # CharacterTraitValue uses ObjectDB FK; CharacterSheet PK == ObjectDB PK
        trait_value, _created = CharacterTraitValue.objects.get_or_create(
            character=self.character_sheet.character,
            trait=self.trait,
            defaults={"value": 10},
        )

        level_ups: list[tuple[int, int]] = []
        current_level: int = trait_value.value

        while True:
            next_level = current_level + 1
            dp_needed = cumulative_dp_for_level(next_level)
            if self.total_earned >= dp_needed:
                level_ups.append((current_level, next_level))
                current_level = next_level
            else:
                break

        if level_ups:
            trait_value.value = current_level
            trait_value.save()

        return level_ups

    class Meta:
        unique_together: ClassVar[list[str]] = ["character_sheet", "trait"]
        ordering: ClassVar[list[str]] = ["character_sheet", "trait"]
        indexes: ClassVar[list[models.Index]] = [models.Index(fields=["character_sheet", "trait"])]

    def __str__(self) -> str:
        return f"{self.character_sheet}: {self.total_earned} dp for {self.trait.name}"


class DevelopmentTransaction(SharedMemoryModel):
    """Audit trail for all development point awards."""

    character_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="development_transactions",
    )
    trait = models.ForeignKey(
        "traits.Trait",
        on_delete=models.CASCADE,
        related_name="development_transactions",
    )
    source = models.CharField(max_length=20, choices=DevelopmentSource.choices)
    amount = models.PositiveIntegerField(
        help_text="Development points awarded and applied",
    )
    reason = models.CharField(max_length=20, choices=ProgressionReason.choices)
    description = models.CharField(max_length=255, blank=True)
    scene = models.ForeignKey(
        "scenes.Scene",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    gm = models.ForeignKey(
        AccountDB,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="development_transactions_created",
    )
    transaction_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-transaction_date"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["character_sheet", "-transaction_date"]),
            models.Index(fields=["trait", "-transaction_date"]),
            models.Index(fields=["scene", "-transaction_date"]),
        ]

    def __str__(self) -> str:
        return f"{self.character_sheet}: +{self.amount} dp for {self.trait.name}"


class WeeklySkillUsage(SharedMemoryModel):
    """Tracks development points earned per trait per week via skill checks.

    Upserted with ``F()`` expressions on each qualifying check. Serves as:

    * Silent dp accumulator (no per-check audit spam)
    * Rust prevention flag (any row = trait was used)
    * Weekly summary data source
    """

    character_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="weekly_skill_usage",
    )
    trait = models.ForeignKey(
        "traits.Trait",
        on_delete=models.CASCADE,
        related_name="weekly_skill_usage",
    )
    game_week = models.ForeignKey(
        "game_clock.GameWeek",
        on_delete=models.CASCADE,
        related_name="skill_usages",
    )
    points_earned = models.PositiveIntegerField(default=0)
    check_count = models.PositiveIntegerField(default=0)
    processed = models.BooleanField(default=False)

    class Meta:
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=["character_sheet", "trait", "game_week"],
                name="unique_skill_usage_per_week",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.character_sheet}: {self.points_earned} dp for "
            f"{self.trait.name} ({self.game_week})"
        )
