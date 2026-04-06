"""Constants and enums for the vitals system.

Character life states, health thresholds, and wound descriptions that are
shared across combat, poison, spells, exhaustion, and other systems.
"""

from django.db import models

# ---------------------------------------------------------------------------
# Character life-state enum
# ---------------------------------------------------------------------------


class CharacterStatus(models.TextChoices):
    """Current life state of a character."""

    ALIVE = "alive", "Alive"
    UNCONSCIOUS = "unconscious", "Unconscious"
    DYING = "dying", "Dying"
    DEAD = "dead", "Dead"


# ---------------------------------------------------------------------------
# Health thresholds
# ---------------------------------------------------------------------------

PERMANENT_WOUND_THRESHOLD: float = 0.5
KNOCKOUT_HEALTH_THRESHOLD: float = 0.2
DEATH_HEALTH_THRESHOLD: int = 0

# ---------------------------------------------------------------------------
# Wound descriptions -- (threshold, description) from healthiest to worst
# ---------------------------------------------------------------------------

WOUND_DESCRIPTIONS: list[tuple[float, str]] = [
    (0.9, "healthy appearance"),
    (0.8, "lightly wounded"),
    (0.7, "wounded"),
    (0.6, "moderately wounded"),
    (0.5, "seriously wounded"),
    (0.4, "badly wounded"),
    (0.3, "critically wounded"),
    (0.2, "near collapse"),
    (0.1, "barely clinging to life"),
    (0.0, "incapacitated"),
]
