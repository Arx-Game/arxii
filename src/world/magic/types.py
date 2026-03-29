from __future__ import annotations

from dataclasses import dataclass, field

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


@dataclass
class RuntimeTechniqueStats:
    """Runtime intensity and control after modifiers.

    MVP: base values only. Future: affinity bonuses, escalation, Audere.
    """

    intensity: int
    control: int


@dataclass
class AnimaCostResult:
    """Result of calculating effective anima cost."""

    base_cost: int
    effective_cost: int
    control_delta: int
    current_anima: int
    deficit: int  # 0 if no overburn

    @property
    def is_overburn(self) -> bool:
        return self.deficit > 0


@dataclass
class OverburnSeverity:
    """Severity classification for anima overburn."""

    label: str
    can_cause_death: bool


@dataclass
class MishapResult:
    """Result of resolving a mishap rider."""

    consequence_label: str
    applied_effect_ids: list[int] = field(default_factory=list)


@dataclass
class TechniqueUseResult:
    """Complete result of using a technique."""

    anima_cost: AnimaCostResult
    overburn_severity: OverburnSeverity | None = None
    confirmed: bool = True  # False if player cancelled at checkpoint
    resolution_result: object | None = None  # ChallengeResolutionResult, etc.
    mishap: MishapResult | None = None
