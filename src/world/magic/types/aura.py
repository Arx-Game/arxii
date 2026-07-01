from __future__ import annotations

from dataclasses import dataclass

from django.db import models


@dataclass
class AuraPercentages:
    """Aura percentages across the three magical affinities."""

    celestial: float
    primal: float
    abyssal: float


@dataclass(frozen=True)
class AuraDrift:
    """Before/after aura percentages from one recompute_aura() call."""

    before: AuraPercentages
    after: AuraPercentages


class AffinityType(models.TextChoices):
    """The three magical affinities."""

    CELESTIAL = "celestial", "Celestial"
    PRIMAL = "primal", "Primal"
    ABYSSAL = "abyssal", "Abyssal"
