"""Models for the goals system.

Characters distribute 30 points across goal domains, gaining bonuses
when pursuing those goals. Goal weights add as situational modifiers
when making checks that align with the goal.

Goal domains are stored as ModifierType entries with category='goal'.
Journals track progress and award XP.
"""

from datetime import timedelta

from django.db import models
from django.utils import timezone

from world.goals.constants import GoalStatus

# Goal domain names for reference (stored as ModifierType with category='goal'):
# - Standing: Social status, reputation, political power
# - Wealth: Material resources, financial security
# - Knowledge: Learning, secrets, understanding
# - Mastery: Personal skill, excellence, achievement
# - Bonds: Relationships, loyalty, connections
# - Drives: (Optional) Survival, basic necessities

# Optional domains don't require point allocation
OPTIONAL_GOAL_DOMAINS = {"Drives"}


class CharacterGoal(models.Model):
    """
    A character's goal allocation in a specific domain.

    Characters have 30 points total to distribute across domains.
    Points in a domain add as a situational bonus when making checks
    that align with the goal.

    Domain is a ModifierType with category='goal'.
    """

    character = models.ForeignKey(
        "objects.ObjectDB",
        on_delete=models.CASCADE,
        related_name="goals",
    )
    domain = models.ForeignKey(
        "mechanics.ModifierType",
        on_delete=models.PROTECT,
        related_name="character_goals",
        limit_choices_to={"category__name": "goal"},
        help_text="Goal domain (ModifierType with category='goal')",
    )
    points = models.PositiveIntegerField(default=0)
    notes = models.TextField(
        blank=True,
        help_text="Freeform notes describing specific goals within this domain.",
    )
    status = models.CharField(
        max_length=20,
        choices=GoalStatus.choices,
        default=GoalStatus.ACTIVE,
        help_text="Current status of this goal.",
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this goal was completed (if applicable).",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["character", "domain"]

    def __str__(self) -> str:
        return f"{self.character} - {self.domain.name}: {self.points}"


class GoalJournal(models.Model):
    """
    Journal entries about goal progress.

    Writing journal entries awards XP and helps players reflect on
    their character's motivations. For roster characters, journals
    provide continuity for new players.
    """

    character = models.ForeignKey(
        "objects.ObjectDB",
        on_delete=models.CASCADE,
        related_name="goal_journals",
    )
    domain = models.ForeignKey(
        "mechanics.ModifierType",
        on_delete=models.PROTECT,
        related_name="goal_journals",
        null=True,
        blank=True,
        limit_choices_to={"category__name": "goal"},
        help_text="Optional: specific goal domain this entry relates to.",
    )
    title = models.CharField(max_length=200)
    content = models.TextField()
    is_public = models.BooleanField(
        default=False,
        help_text="Public journals can be read by other players.",
    )
    xp_awarded = models.PositiveIntegerField(
        default=0,
        help_text="XP awarded for this journal entry.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.character} - {self.title}"


class GoalRevision(models.Model):
    """
    Tracks when characters revise their goals.

    Characters can revise goals once per week. This model tracks
    the last revision to enforce that limit.
    """

    character = models.OneToOneField(
        "objects.ObjectDB",
        on_delete=models.CASCADE,
        related_name="goal_revision",
    )
    last_revised_at = models.DateTimeField(default=timezone.now)

    def can_revise(self) -> bool:
        """Check if a week has passed since last revision."""
        return timezone.now() >= self.last_revised_at + timedelta(weeks=1)

    def mark_revised(self) -> None:
        """Mark goals as revised now."""
        self.last_revised_at = timezone.now()
        self.save(update_fields=["last_revised_at"])

    def __str__(self) -> str:
        return f"{self.character} - Last revised: {self.last_revised_at}"


class GoalInstance(models.Model):
    """
    Tracks each time a goal was applied to a roll.

    Used for Legend claims when goal is completed. The check FK
    is nullable until the Check model is implemented.
    """

    goal = models.ForeignKey(
        CharacterGoal,
        on_delete=models.CASCADE,
        related_name="instances",
    )
    # TODO: Add check FK when Check model exists
    # check = models.ForeignKey(
    #     "checks.Check",
    #     on_delete=models.SET_NULL,
    #     null=True,
    #     blank=True,
    #     related_name="goal_instances",
    # )
    roll_story = models.TextField(
        help_text="Player's narrative of how this goal applied to the roll",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.goal} instance at {self.created_at}"
