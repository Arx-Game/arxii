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

from world.progression.types import DevelopmentSource, ProgressionReason
from world.traits.models import CharacterTraitValue


class ExperiencePointsData(models.Model):
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
    def current_available(self):
        """XP currently available to spend (calculated property)."""
        total_earned = cast(int, self.total_earned)
        total_spent = cast(int, self.total_spent)
        return total_earned - total_spent

    def clean(self):
        """Validate XP totals are consistent."""
        super().clean()
        if cast(int, self.total_spent) > cast(int, self.total_earned):
            msg = "Total spent cannot exceed total earned XP"
            raise ValidationError(msg)

    def can_spend(self, amount):
        """Check if account has enough XP to spend the given amount."""
        return self.current_available >= amount

    def spend_xp(self, amount):
        """Spend XP if available, updating totals."""
        if not self.can_spend(amount):
            return False
        self.total_spent += amount
        self.save()
        return True

    def award_xp(self, amount):
        """Award XP to the account."""
        self.total_earned += amount
        self.save()

    def __str__(self):
        return f"{self.account.username}: {self.current_available}/{self.total_earned} XP"

    class Meta:
        verbose_name = "Experience Points Data"
        verbose_name_plural = "Experience Points Data"


class XPTransaction(models.Model):
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

    def __str__(self):
        amount_value = cast(int, self.amount)
        sign = "+" if amount_value >= 0 else ""
        return f"{self.account.username}: {sign}{amount_value} XP ({self.get_reason_display()})"

    class Meta:
        ordering: ClassVar[list[str]] = ["-transaction_date"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["account", "-transaction_date"]),
            models.Index(fields=["character", "-transaction_date"]),
        ]


class DevelopmentPoints(models.Model):
    """Development points earned by characters through activity."""

    character = models.ForeignKey(
        "objects.ObjectDB",
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
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

    def award_points(self, amount):
        """Award development points and automatically apply them to the trait."""
        self.total_earned += amount
        self.save()

        trait_value, _created = CharacterTraitValue.objects.get_or_create(
            character=self.character,
            trait=self.trait,
            defaults={"value": 0},
        )

        new_value = trait_value.value + amount
        # Check if crossing a major threshold that requires unlock
        if new_value // 10 > trait_value.value // 10:
            threshold = (new_value // 10) * 10
            if not self._has_rating_unlock(threshold):
                new_value = threshold - 1  # Cap just below threshold

        trait_value.value = new_value
        trait_value.save()

    def _has_rating_unlock(self, rating):  # noqa: ARG002
        """Check if character has unlocked the given rating for this trait."""
        # With the new unlock system, trait ratings don't require separate unlocks
        # They auto-apply through development points. Only class levels require unlocks.
        return True

    class Meta:
        unique_together: ClassVar[list[str]] = ["character", "trait"]
        ordering: ClassVar[list[str]] = ["character", "trait"]
        indexes: ClassVar[list[models.Index]] = [models.Index(fields=["character", "trait"])]

    def __str__(self):
        return f"{self.character.key}: {self.total_earned} development points for {self.trait.name}"


class DevelopmentTransaction(models.Model):
    """Audit trail for all development point awards."""

    character = models.ForeignKey(
        "objects.ObjectDB",
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
            models.Index(fields=["character", "-transaction_date"]),
            models.Index(fields=["trait", "-transaction_date"]),
            models.Index(fields=["scene", "-transaction_date"]),
        ]

    def __str__(self):
        return f"{self.character.key}: +{self.amount} points for {self.trait.name}"
