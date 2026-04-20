from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from django.db import models

if TYPE_CHECKING:
    from world.checks.types import CheckResult
    from world.conditions.models import ConditionInstance
    from world.magic.models import (
        MagicalAlterationEvent,
        MagicalAlterationTemplate,
        PendingAlteration,
        Thread,
    )
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


@dataclass
class TechniqueUseResult:
    """Complete result of using a technique."""

    anima_cost: AnimaCostResult
    confirmed: bool = True  # False if player cancelled at checkpoint
    resolution_result: object | None = None  # ChallengeResolutionResult, etc.
    mishap: MishapResult | None = None
    soulfray_result: SoulfrayResult | None = None
    soulfray_warning: SoulfrayWarning | None = None


@dataclass(frozen=True)
class ThreadImbueResult:
    """Result of spend_resonance_for_imbuing (Spec A §3.2)."""

    resonance_spent: int
    developed_points_added: int
    levels_gained: int
    new_level: int
    new_developed_points: int
    blocked_by: Literal["NONE", "XP_LOCK", "ANCHOR_CAP", "PATH_CAP", "INSUFFICIENT_BUCKET"]


@dataclass(frozen=True)
class ThreadXPLockProspect:
    """A thread that is close to an XP-locked level boundary (Spec A §3.6)."""

    thread: Thread
    boundary_level: int
    xp_cost: int
    dev_points_to_boundary: int


class AlterationGateError(Exception):
    """Raised when a character tries to spend advancement points while
    having unresolved magical alterations."""

    user_message = (
        "You have an unresolved magical alteration. "
        "Visit the alteration screen to resolve it before "
        "spending advancement points."
    )


class AlterationResolutionError(Exception):
    """Raised when condition application fails during alteration resolution."""

    user_message = (
        "The magical alteration could not be applied due to a "
        "condition interaction. Please contact staff."
    )


@dataclass(frozen=True)
class PendingAlterationResult:
    """Result of creating or escalating a PendingAlteration."""

    pending: PendingAlteration
    created: bool  # True if new, False if escalated
    previous_tier: int | None  # Non-null if escalated


@dataclass(frozen=True)
class AlterationResolutionResult:
    """Result of resolving a PendingAlteration."""

    pending: PendingAlteration
    template: MagicalAlterationTemplate
    condition_instance: ConditionInstance
    event: MagicalAlterationEvent
