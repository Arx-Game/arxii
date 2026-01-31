"""Constants for the goals system."""

from django.db import models


class GoalStatus(models.TextChoices):
    """Status of a character goal."""

    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    ABANDONED = "abandoned", "Abandoned"
