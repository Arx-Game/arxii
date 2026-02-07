"""Constants for the mechanics system."""

from django.db import models

# ModifierCategory name constants (must match fixture data)
STAT_CATEGORY_NAME = "stat"
GOAL_CATEGORY_NAME = "goal"
GOAL_PERCENT_CATEGORY_NAME = "goal_percent"
GOAL_POINTS_CATEGORY_NAME = "goal_points"
RESONANCE_CATEGORY_NAME = "resonance"


class ResonanceAffinity(models.TextChoices):
    """Affinity type for resonances (celestial, abyssal, primal)."""

    CELESTIAL = "celestial", "Celestial"
    ABYSSAL = "abyssal", "Abyssal"
    PRIMAL = "primal", "Primal"
