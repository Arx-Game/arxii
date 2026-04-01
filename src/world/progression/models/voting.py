"""
Voting models for the progression system.

Players get 7 base votes per week + 1 bonus per scene attended. Votes are
toggleable (cast/uncast), persist with a ``processed`` flag (set by weekly
cron), and feed XP calculations.
"""

from django.db import models
from evennia.accounts.models import AccountDB
from evennia.utils.idmapper.models import SharedMemoryModel

from world.progression.constants import VoteTargetType


class WeeklyVoteBudget(SharedMemoryModel):
    """Tracks how many votes an account has available for a given week.

    ``base_votes`` starts at 7. ``scene_bonus_votes`` is incremented by 1
    for each scene the account participates in during the week.
    ``votes_spent`` is updated as the player casts/uncasts votes.
    """

    account = models.ForeignKey(
        AccountDB,
        on_delete=models.CASCADE,
        related_name="weekly_vote_budgets",
    )
    week_start = models.DateField(
        help_text="Monday of the voting week (ISO week start)",
    )
    base_votes = models.PositiveIntegerField(default=7)
    scene_bonus_votes = models.PositiveIntegerField(default=0)
    votes_spent = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["account", "week_start"],
                name="unique_account_week_budget",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.account} week {self.week_start}: {self.votes_remaining} remaining"

    @property
    def votes_remaining(self) -> int:
        """Number of votes the account can still cast this week."""
        return self.base_votes + self.scene_bonus_votes - self.votes_spent


class WeeklyVote(SharedMemoryModel):
    """A single vote cast by a player on a piece of content.

    ``target_type`` + ``target_id`` form a generic FK without database-level
    cascades -- cleanup is handled by service functions when targets are deleted.
    """

    voter = models.ForeignKey(
        AccountDB,
        on_delete=models.CASCADE,
        related_name="weekly_votes",
    )
    week_start = models.DateField(
        help_text="Monday of the voting week (ISO week start)",
    )
    target_type = models.CharField(
        max_length=25,
        choices=VoteTargetType.choices,
    )
    target_id = models.PositiveIntegerField(
        help_text="PK of the voted-on object (not a FK -- no cascades)",
    )
    author_account = models.ForeignKey(
        AccountDB,
        on_delete=models.CASCADE,
        related_name="votes_received",
        help_text="Account that authored the voted-on content",
    )
    processed = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Set True by the weekly cron after XP is awarded",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["voter", "target_type", "target_id", "week_start"],
                name="unique_vote_per_target_per_week",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.voter} -> {self.target_type}:{self.target_id} (week {self.week_start})"
