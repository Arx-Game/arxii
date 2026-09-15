"""Constants for the goals system."""

from django.db import models


class GoalHorizon(models.TextChoices):
    """When a goal is meant to land (#3621). Goals are numbered within a horizon."""

    SHORT_TERM = "short_term", "Short term"
    LONG_TERM = "long_term", "Long term"


class GoalStatus(models.TextChoices):
    """Status of a character goal."""

    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    ABANDONED = "abandoned", "Abandoned"


# XP for the 1st/2nd/3rd goal-progress log each game week; nothing after that.
# Mirrors the shape of world.journals JOURNAL_POST_XP ([5, 2, 1]) with lower values —
# a goal log is a lighter act than a journal post, and 1 XP is the amount this
# surface has always claimed to award.
GOAL_LOG_XP = [1, 1, 1]
