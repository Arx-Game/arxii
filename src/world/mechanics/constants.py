"""Constants for the mechanics system."""

from django.db import models


class ResonanceAffinity(models.TextChoices):
    """Affinity type for resonances (celestial, abyssal, primal)."""

    CELESTIAL = "celestial", "Celestial"
    ABYSSAL = "abyssal", "Abyssal"
    PRIMAL = "primal", "Primal"
