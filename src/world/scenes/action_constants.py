"""Constants for scene action requests."""

from django.db import models


class ActionRequestStatus(models.TextChoices):
    """Status of a scene action request."""

    PENDING = "pending", "Pending"
    ACCEPTED = "accepted", "Accepted"
    DENIED = "denied", "Denied"
    RESOLVED = "resolved", "Resolved"
    EXPIRED = "expired", "Expired"


class DifficultyChoice(models.TextChoices):
    """Difficulty level for scene action checks."""

    TRIVIAL = "trivial", "Trivial"
    EASY = "easy", "Easy"
    NORMAL = "normal", "Normal"
    HARD = "hard", "Hard"
    DAUNTING = "daunting", "Daunting"


class ConsentDecision(models.TextChoices):
    """Player consent decision for an action targeting them."""

    ACCEPT = "accept", "Accept"
    DENY = "deny", "Deny"


DIFFICULTY_VALUES: dict[str, int] = {
    DifficultyChoice.TRIVIAL: 15,
    DifficultyChoice.EASY: 30,
    DifficultyChoice.NORMAL: 45,
    DifficultyChoice.HARD: 60,
    DifficultyChoice.DAUNTING: 75,
}
