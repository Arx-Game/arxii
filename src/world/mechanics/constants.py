"""Constants for the mechanics system."""

from django.db import models

# ModifierCategory name constants (must match fixture data)
STAT_CATEGORY_NAME = "stat"


class ResonanceAffinity(models.TextChoices):
    """Affinity type for resonances (celestial, abyssal, primal)."""

    CELESTIAL = "celestial", "Celestial"
    ABYSSAL = "abyssal", "Abyssal"
    PRIMAL = "primal", "Primal"
