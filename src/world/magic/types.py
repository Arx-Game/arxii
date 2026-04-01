from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from django.db import models

if TYPE_CHECKING:
    from world.checks.types import CheckResult
    from world.mechanics.types import AppliedEffect


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
    """Runtime intensity and control after combining all modifier streams.

    Produced by combining:
    - Technique base values (intensity, control)
    - Identity modifiers (CharacterModifier targeting technique_stat category)
    - Process modifiers (CharacterEngagement.intensity_modifier / control_modifier)
    - Social safety bonus (+10 control when character is not engaged)
    - IntensityTier control modifier (penalty applied based on final runtime intensity)
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
class WarpWarning:
    """Warning information for the safety checkpoint based on current Warp stage."""

    stage_name: str
    stage_description: str
    has_death_risk: bool


@dataclass
class WarpResult:
    """Result of Warp accumulation in Step 7 of use_technique()."""

    severity_added: int
    stage_name: str | None
    stage_advanced: bool
    resilience_check: CheckResult | None = None
    stage_consequence: AppliedEffect | None = None


@dataclass
class MishapResult:
    """Result of resolving a mishap rider."""

    consequence_label: str
    applied_effect_ids: list[int] = field(default_factory=list)


@dataclass
class TechniqueUseResult:
    """Complete result of using a technique."""

    anima_cost: AnimaCostResult
    confirmed: bool = True  # False if player cancelled at checkpoint
    resolution_result: object | None = None  # ChallengeResolutionResult, etc.
    mishap: MishapResult | None = None
    warp_result: WarpResult | None = None
    warp_warning: WarpWarning | None = None
