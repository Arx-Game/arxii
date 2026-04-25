"""
Condition System Types

Dataclasses and type definitions for the conditions service layer.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from django.db import models

if TYPE_CHECKING:
    from django.db.models import Q

    from world.conditions.models import (
        ConditionInstance,
        ConditionStage,
        ConditionTemplate,
        DamageType,
        TreatmentAttempt,
    )
    from world.traits.models import CheckOutcome


class AdvancementOutcome(models.TextChoices):
    """Outcome of a stage-advancement check on a ConditionInstance."""

    NO_CHANGE = "NO_CHANGE", "No stage change"
    HELD = "HELD", "Threshold crossed but resist check passed"
    ADVANCED = "ADVANCED", "Stage advanced"


class AdvancementResistFailureKind(models.TextChoices):
    """Behavior when severity reaches a stage's threshold."""

    ADVANCE_AT_THRESHOLD = "ADVANCE_AT_THRESHOLD", "Advance immediately on threshold crossing"
    HOLD_OVERFLOW = "HOLD_OVERFLOW", "Severity accumulates over threshold; each accrual rolls"


@dataclass
class ApplyConditionResult:
    """Result of attempting to apply a condition."""

    success: bool
    instance: "ConditionInstance | None" = None
    message: str = ""
    stacks_added: int = 0
    was_prevented: bool = False
    prevented_by: "ConditionTemplate | None" = None
    removed_conditions: list["ConditionTemplate"] = field(default_factory=list)
    applied_conditions: list["ConditionInstance"] = field(default_factory=list)


@dataclass
class DamageInteractionResult:
    """Result of processing damage against a conditioned target."""

    damage_modifier_percent: int = 0
    removed_conditions: list["ConditionInstance"] = field(default_factory=list)
    applied_conditions: list["ConditionInstance"] = field(default_factory=list)


@dataclass
class CapabilityStatus:
    """Status of a capability for a target, computed from active conditions."""

    value: int = 0
    condition_contributions: list[tuple["ConditionInstance", int]] = field(default_factory=list)


@dataclass
class CheckModifierResult:
    """Total modifier for a check type."""

    total_modifier: int = 0
    breakdown: list[tuple["ConditionInstance", int]] = field(default_factory=list)


@dataclass
class ResistanceModifierResult:
    """Total resistance modifier for a damage type."""

    total_modifier: int = 0
    breakdown: list[tuple["ConditionInstance", int]] = field(default_factory=list)


@dataclass
class RoundTickResult:
    """Result of processing a round tick for a target."""

    damage_dealt: list[tuple["DamageType", int]] = field(default_factory=list)
    progressed_conditions: list["ConditionInstance"] = field(default_factory=list)
    expired_conditions: list["ConditionInstance"] = field(default_factory=list)
    removed_conditions: list["ConditionInstance"] = field(default_factory=list)


@dataclass
class EffectLookups:
    """Lookup tables for resolving which ConditionInstance an effect belongs to.

    Built from a list of active ConditionInstances, then passed to batch
    aggregation functions so they can resolve effect rows back to instances.
    """

    effect_filter: "Q"
    instance_by_condition: dict[int, "ConditionInstance"]
    instance_by_stage: dict[int, "ConditionInstance"]


@dataclass
class CapabilitySummary:
    """Aggregated capability effects across all active conditions."""

    values: dict[str, int] = field(default_factory=dict)


@dataclass
class InteractionResult:
    """Result of processing condition-condition interactions."""

    removed: list["ConditionTemplate"] = field(default_factory=list)
    applied: list["ConditionInstance"] = field(default_factory=list)


@dataclass
class SeverityAdvanceResult:
    """Result of advancing a condition's severity."""

    previous_stage: "ConditionStage | None"
    new_stage: "ConditionStage | None"
    stage_changed: bool
    total_severity: int
    outcome: AdvancementOutcome = AdvancementOutcome.NO_CHANGE  # NEW field, defaulted


@dataclass
class ConditionStageAdvanceCheckPayload:
    """Payload for the CONDITION_STAGE_ADVANCE_CHECK_ABOUT_TO_FIRE event.

    Mutable so reactive triggers can adjust difficulty or bonuses before
    the resist check resolves (Scope 5.5 MODIFY_PAYLOAD pattern).
    """

    instance: "ConditionInstance"
    target_stage: "ConditionStage"
    base_difficulty: int


@dataclass(frozen=True)
class SeverityDecayResult:
    """Result of decaying a condition's severity."""

    previous_stage: "ConditionStage | None"
    new_stage: "ConditionStage | None"
    new_severity: int
    resolved: bool


@dataclass(frozen=True)
class DecayTickSummary:
    """Summary of a scheduler-driven decay tick over all opt-in conditions."""

    examined: int
    ticked: int
    engagement_blocked: int
    severity_gated: int


@dataclass(frozen=True)
class TreatmentOutcome:
    """Result returned by perform_treatment.

    Captures what happened: which attempt was persisted, the raw CheckOutcome
    row, whether any severity or tier reduction was applied, how much backlash
    the helper received, and whether the target effect was fully resolved.
    """

    attempt: "TreatmentAttempt"
    outcome: "CheckOutcome"
    effect_applied: bool
    severity_reduced: int
    tiers_reduced: int
    helper_backlash_applied: int
    target_resolved: bool
