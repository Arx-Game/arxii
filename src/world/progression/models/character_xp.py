"""
Character-level XP models.

Tracks XP earned by individual characters, with a transferable flag to
distinguish locked XP (e.g., from CG conversion) from freely transferable XP.
"""

from typing import ClassVar, cast

from django.core.exceptions import ValidationError
from django.db import models

from world.progression.types import ProgressionReason


class CharacterXP(models.Model):
    """Per-character XP balance, partitioned by transferability."""

    character = models.ForeignKey(
        "objects.ObjectDB",
        on_delete=models.CASCADE,
        related_name="character_xp",
    )
    total_earned = models.PositiveIntegerField(
        default=0,
        help_text="Total XP earned",
    )
    total_spent = models.PositiveIntegerField(
        default=0,
        help_text="Total XP spent",
    )
    transferable = models.BooleanField(
        default=True,
        help_text="If False, XP is locked to this character and cannot be transferred",
    )
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

    @property
    def current_available(self) -> int:
        """XP currently available to spend."""
        return cast(int, self.total_earned) - cast(int, self.total_spent)

    def clean(self):
        """Validate XP totals are consistent."""
        super().clean()
        if cast(int, self.total_spent) > cast(int, self.total_earned):
            msg = "Total spent cannot exceed total earned XP"
            raise ValidationError(msg)

    def can_spend(self, amount: int) -> bool:
        """Check if enough XP is available to spend."""
        return self.current_available >= amount

    def spend_xp(self, amount: int) -> bool:
        """Spend XP if available."""
        if not self.can_spend(amount):
            return False
        self.total_spent += amount
        self.save(update_fields=["total_spent", "updated_date"])
        return True

    def award_xp(self, amount: int) -> None:
        """Award XP."""
        self.total_earned += amount
        self.save(update_fields=["total_earned", "updated_date"])

    def __str__(self):
        lock_label = "locked" if not self.transferable else "transferable"
        return (
            f"{self.character.key}: {self.current_available}/{self.total_earned} XP ({lock_label})"
        )

    class Meta:
        unique_together: ClassVar[list[str]] = ["character", "transferable"]
        verbose_name = "Character XP"
        verbose_name_plural = "Character XP"


class CharacterXPTransaction(models.Model):
    """Audit trail for character-level XP changes."""

    character = models.ForeignKey(
        "objects.ObjectDB",
        on_delete=models.CASCADE,
        related_name="character_xp_transactions",
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
        help_text="Human-readable description",
    )
    transferable = models.BooleanField(
        default=True,
        help_text="Whether this XP is transferable",
    )
    transaction_date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        amount_value = cast(int, self.amount)
        sign = "+" if amount_value >= 0 else ""
        return f"{self.character.key}: {sign}{amount_value} XP ({self.get_reason_display()})"

    class Meta:
        ordering: ClassVar[list[str]] = ["-transaction_date"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["character", "-transaction_date"]),
        ]
