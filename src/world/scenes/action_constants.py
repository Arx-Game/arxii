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


class CastPullTier(models.IntegerChoices):
    """Paid pull tiers declarable alongside a standalone cast (#854)."""

    TIER_1 = 1, "Tier 1"
    TIER_2 = 2, "Tier 2"
    TIER_3 = 3, "Tier 3"


CAST_ACTION_KEY = "cast"  # sentinel marking a standalone cast request

# Authored difficulty bands keyed by technique intensity ceiling. Single source
# of truth (no inline magic numbers in logic). On the same 0-75 scale as
# DIFFICULTY_VALUES so consequence resolution thresholds line up.
CAST_DIFFICULTY_BANDS: tuple[tuple[int, int], ...] = (
    (2, 15),
    (4, 30),
    (6, 45),
    (8, 60),
    (9999, 75),
)
