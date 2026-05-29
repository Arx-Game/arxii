"""Constants and enums for the vitals system.

Character life states, health thresholds, and wound descriptions that are
shared across combat, poison, spells, exhaustion, and other systems.
"""

from django.db import models

# ---------------------------------------------------------------------------
# Character life-state enum
# ---------------------------------------------------------------------------


class CharacterLifeState(models.TextChoices):
    """Mortality axis only. Consciousness/dying live in the conditions system."""

    ALIVE = "alive", "Alive"
    DEAD = "dead", "Dead"


# ---------------------------------------------------------------------------
# Derived wire-status strings
# ---------------------------------------------------------------------------
# Coarse, read-only status surface exposed by the combat API. Derived at read
# time from life_state + active conditions + agency — NOT a persisted field.
# The richer frontend status surface is tracked by #521/#522.

DERIVED_STATUS_DEAD: str = "dead"
DERIVED_STATUS_DYING: str = "dying"
DERIVED_STATUS_INCAPACITATED: str = "incapacitated"
DERIVED_STATUS_ALIVE: str = "alive"


# ---------------------------------------------------------------------------
# Health thresholds
# ---------------------------------------------------------------------------

PERMANENT_WOUND_THRESHOLD: float = 0.5
KNOCKOUT_HEALTH_THRESHOLD: float = 0.2
DEATH_HEALTH_THRESHOLD: float = 0.0

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

# ---------------------------------------------------------------------------
# Survivability check difficulty scaling
# ---------------------------------------------------------------------------

# Base difficulty for knockout check at exactly 20% health
KNOCKOUT_BASE_DIFFICULTY: int = 20
# Additional difficulty per percentage point below 20% health
KNOCKOUT_SCALING_PER_PERCENT: int = 3

# Base difficulty for death check at exactly 0% health
DEATH_BASE_DIFFICULTY: int = 30
# Additional difficulty per percentage point below 0%
DEATH_SCALING_PER_PERCENT: int = 5

# Base difficulty for permanent wound check at exactly 50% damage
WOUND_BASE_DIFFICULTY: int = 15
# Additional difficulty per percentage point of max_health over threshold
WOUND_SCALING_PER_PERCENT: int = 2

# ---------------------------------------------------------------------------
# Survivability resistance checks (seeded on first use, like fatigue endurance)
# ---------------------------------------------------------------------------

ENDURANCE_CHECK_NAME: str = "Endurance"  # shared: knockout + permanent wound
DEATH_CHECK_NAME: str = "Mortal Resolve"  # distinct, high-stakes (death)
SURVIVABILITY_CHECK_CATEGORY: str = "Survival"
