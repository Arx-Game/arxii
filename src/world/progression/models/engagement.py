"""
Weekly social-engagement pending ledger.

Tracks per-account weekly accrual of good-sport credit before it is
granted, with a child table for distinct-initiator anti-farm tracking.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from django.db import models
from evennia.accounts.models import AccountDB
from evennia.utils.idmapper.models import SharedMemoryModel

if TYPE_CHECKING:
    from world.game_clock.models import GameWeek


class WeeklySocialEngagement(SharedMemoryModel):
    """
    Per-account weekly accumulator for social-engagement credit.

    Created on first accrual for the account; reset when the game week
    changes (lazy, on next accrue() call or explicit reset_week()).
    """

    account = models.OneToOneField(
        AccountDB,
        on_delete=models.CASCADE,
        related_name="weekly_social_engagement",
    )
    game_week = models.ForeignKey(
        "game_clock.GameWeek",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="social_engagement_trackers",
        help_text="GameWeek these counters belong to.",
    )
    pending_points = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal(0),
        help_text="Points accrued this week, pending grant.",
    )
    engagement_events = models.PositiveIntegerField(
        default=0,
        help_text=(
            "Count of good-sport acceptances this week — each is one attempt in the "
            "diminishing-chance grant curve (#1698)."
        ),
    )
    granted = models.BooleanField(
        default=False,
        help_text="Whether this week's pending points have been granted.",
    )

    class Meta:
        verbose_name = "Weekly Social Engagement"
        verbose_name_plural = "Weekly Social Engagements"

    @property
    def distinct_initiators(self) -> int:
        """Derive count of unique initiators from child rows (no stored counter)."""
        return self.initiators.count()

    def needs_reset(self, current_week: GameWeek) -> bool:
        """Return True if the tracker belongs to a different game week."""
        return self.game_week_id != current_week.pk

    def reset_week(self, current_week: GameWeek) -> None:
        """
        Reset all weekly counters to zero and set the current game week.

        Also deletes all child WeeklyEngagementInitiator rows so distinct-
        initiator tracking starts fresh.
        """
        self.initiators.all().delete()
        self.pending_points = Decimal(0)
        self.engagement_events = 0
        self.granted = False
        self.game_week = current_week
        self.save(
            update_fields=[
                "pending_points",
                "engagement_events",
                "granted",
                "game_week",
            ]
        )

    def __str__(self) -> str:
        return f"WeeklySocialEngagement for {self.account}"


class WeeklyEngagementInitiator(SharedMemoryModel):
    """
    Records which accounts have already accrued points toward a given ledger
    this week.  Used to count distinct initiators without a JSON field.
    """

    ledger = models.ForeignKey(
        WeeklySocialEngagement,
        on_delete=models.CASCADE,
        related_name="initiators",
    )
    initiator_account = models.ForeignKey(
        AccountDB,
        on_delete=models.CASCADE,
        related_name="+",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["ledger", "initiator_account"],
                name="uniq_engagement_initiator",
            )
        ]
        verbose_name = "Weekly Engagement Initiator"
        verbose_name_plural = "Weekly Engagement Initiators"

    def __str__(self) -> str:
        return f"{self.initiator_account} → {self.ledger}"
