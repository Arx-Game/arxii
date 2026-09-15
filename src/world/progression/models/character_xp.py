"""
Character-level XP models.

XP itself is account-scoped (ADR-0053). These rows record what each *character* has
to do with it, and ``transferable`` says which of two things a row is:

* ``transferable=True`` — the character's **attribution ledger** (#3748). Written by
  every award and every purchase (``world.progression.services.xp_ledger``), it
  answers "what has this player earned on, and invested in, this character" — the
  number the death-kudos cap is sized on (ADR-0131) and that character-loss
  reimbursement will read. It is not a pool: nothing is drawn from it, and
  ``total_spent`` may exceed ``total_earned``, because XP earned on one character is
  routinely spent on another.
* ``transferable=False`` — a genuine **locked pool**, written once by CG conversion
  (``award_cg_conversion_xp``) for unspent CG points. This one *is* drawn from, so
  the no-overdraft invariant applies to it.
"""

from typing import ClassVar, cast

from django.core.exceptions import ValidationError
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.progression.types import ProgressionReason


class CharacterXP(SharedMemoryModel):
    """Per-character XP balance, partitioned by transferability."""

    character = models.ForeignKey(
        "arxii.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="character_xp",
    )
    total_earned = models.PositiveIntegerField(
        default=0,
        help_text="Lifetime XP earned on this character",
    )
    total_spent = models.PositiveIntegerField(
        default=0,
        help_text="Lifetime XP spent on this character (may exceed earned)",
    )
    transferable = models.BooleanField(
        default=True,
        help_text="If False, XP is a pool locked to this character; if True, an attribution ledger",
    )
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

    @property
    def current_available(self) -> int:
        """Unspent XP in a locked pool.

        Meaningless on a transferable attribution row, where the two counters are
        independent lifetime totals and this can legitimately go negative.
        """
        return cast(int, self.total_earned) - cast(int, self.total_spent)

    def clean(self) -> None:
        """Validate a locked pool has not overdrawn.

        Only locked (``transferable=False``) rows are pools. A transferable row is
        the attribution ledger (#3748): spending more on a character than was ever
        earned on them is the ordinary case for anyone's second character, so the
        no-overdraft rule would reject correct data.
        """
        super().clean()
        if self.transferable:
            return
        if cast(int, self.total_spent) > cast(int, self.total_earned):
            msg = "Total spent cannot exceed total earned XP"
            raise ValidationError(msg)

    def can_spend(self, amount: int) -> bool:
        """Check if enough XP is available to spend from a locked pool."""
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

    def __str__(self) -> str:
        lock_label = "locked" if not self.transferable else "transferable"
        return (
            f"{self.character.key}: {self.current_available}/{self.total_earned} XP ({lock_label})"
        )

    class Meta:
        verbose_name = "Character XP"
        verbose_name_plural = "Character XP"
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["character", "transferable"]),
        ]


class CharacterXPTransaction(SharedMemoryModel):
    """Audit trail for character-level XP changes."""

    character = models.ForeignKey(
        "arxii.CharacterSheet",
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

    def __str__(self) -> str:
        amount_value = cast(int, self.amount)
        sign = "+" if amount_value >= 0 else ""
        return f"{self.character.key}: {sign}{amount_value} XP ({self.get_reason_display()})"

    class Meta:
        ordering: ClassVar[list[str]] = ["-transaction_date"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["character", "-transaction_date"]),
        ]
