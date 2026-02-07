from dataclasses import dataclass

from django.db import models


@dataclass
class AuraPercentages:
    """Aura percentages across the three magical affinities."""

    celestial: float
    primal: float
    abyssal: float


class AffinityType(models.TextChoices):
    """The three magical affinities."""

    CELESTIAL = "celestial", "Celestial"
    PRIMAL = "primal", "Primal"
    ABYSSAL = "abyssal", "Abyssal"


class ResonanceScope(models.TextChoices):
    """How a resonance attachment affects targets."""

    SELF = "self", "Self Only"
    AREA = "area", "Area Effect"


class ResonanceStrength(models.TextChoices):
    """The strength of a resonance attachment."""

    MINOR = "minor", "Minor"
    MODERATE = "moderate", "Moderate"
    MAJOR = "major", "Major"


class AnimaRitualCategory(models.TextChoices):
    """Categories of anima recovery rituals."""

    SOLITARY = "solitary", "Solitary"
    COLLABORATIVE = "collaborative", "Collaborative"
    ENVIRONMENTAL = "environmental", "Environmental"
    CEREMONIAL = "ceremonial", "Ceremonial"


class ThreadAxis(models.TextChoices):
    """The axes along which magical threads (relationships) are measured."""

    ROMANTIC = "romantic", "Romantic"
    TRUST = "trust", "Trust"
    RIVALRY = "rivalry", "Rivalry"
    PROTECTIVE = "protective", "Protective"
    ENMITY = "enmity", "Enmity"
