from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.checks.types import CheckResult
    from world.magic.models import Resonance, Technique
    from world.mechanics.types import AppliedEffect


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
class SoulfrayWarning:
    """Warning information for the safety checkpoint based on current Soulfray stage."""

    stage_name: str
    stage_description: str
    has_death_risk: bool


@dataclass
class SoulfrayResult:
    """Result of Soulfray accumulation in Step 7 of use_technique()."""

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


@dataclass(frozen=True)
class ResonanceInvolvement:
    """Per-resonance participation summary for one technique cast.

    Used by the per-cast corruption hook (Task 2/3) to compute corruption
    accrual per resonance.
    """

    resonance: Resonance
    stat_bonus_contribution: int  # share of runtime intensity attributable to this resonance
    thread_pull_resonance_spent: int  # sum of CombatPull.resonance_spent for active pulls


@dataclass
class TechniqueUseResult:
    """Complete result of using a technique."""

    anima_cost: AnimaCostResult
    confirmed: bool = True  # False if player cancelled at checkpoint
    resolution_result: object | None = None  # ChallengeResolutionResult, etc.
    mishap: MishapResult | None = None
    soulfray_result: SoulfrayResult | None = None
    soulfray_warning: SoulfrayWarning | None = None
    technique: Technique | None = None  # The cast technique
    was_deficit: bool = False  # True if the cast triggered anima overburn
    was_mishap: bool = False  # True if a mishap rider was applied
    was_audere: bool = False  # True if the character was in Audere during the cast
    resonance_involvements: tuple[ResonanceInvolvement, ...] = ()
    corruption_summary: object | None = None  # Placeholder for Task 3 CorruptionAccrualSummary
