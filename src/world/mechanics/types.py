"""
Mechanics System Types

Dataclasses and type definitions for the mechanics service layer.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.checks.types import CheckResult
    from world.mechanics.models import ChallengeConsequence

from world.mechanics.constants import CapabilitySourceType, DifficultyIndicator


@dataclass
class ModifierSourceDetail:
    """Single modifier source with calculation details."""

    source_name: str
    base_value: int
    amplification: int
    final_value: int
    is_amplifier: bool
    blocked_by_immunity: bool


@dataclass
class ModifierBreakdown:
    """Full breakdown for a modifier target."""

    modifier_target_name: str
    sources: list[ModifierSourceDetail]
    total: int
    has_immunity: bool
    negatives_blocked: int


@dataclass
class CapabilitySource:
    """A single source of a Capability for a character."""

    capability_name: str
    capability_id: int
    value: int
    source_type: CapabilitySourceType
    source_name: str  # e.g., "Flame Lance", "Strength"
    source_id: int
    effect_property_ids: list[int] = field(default_factory=list)
    prerequisite_id: int | None = None


@dataclass
class AvailableAction:
    """An Action available to a character for a specific Challenge."""

    application_id: int
    application_name: str
    capability_source: CapabilitySource
    challenge_instance_id: int
    challenge_name: str
    approach_id: int | None
    check_type_name: str
    display_name: str
    custom_description: str
    difficulty_indicator: DifficultyIndicator


@dataclass
class CooperativeAction:
    """A cooperative Action combining multiple characters."""

    application_id: int
    application_name: str
    challenge_instance_id: int
    challenge_name: str
    participants: list[AvailableAction] = field(default_factory=list)


class ChallengeResolutionError(Exception):
    """Raised when challenge resolution is called with invalid state."""


@dataclass
class AppliedEffect:
    """Record of a single effect that was applied or skipped."""

    effect_type: str
    description: str
    applied: bool
    skip_reason: str = ""


@dataclass
class ConsequenceDisplay:
    """Single consequence for frontend roulette display."""

    label: str
    tier_name: str
    weight: int
    is_selected: bool


@dataclass
class ChallengeResolutionResult:
    """Full result from resolve_challenge()."""

    challenge_instance_id: int
    challenge_name: str
    approach_name: str
    check_result: "CheckResult"
    consequence: "ChallengeConsequence"
    applied_effects: list[AppliedEffect]
    resolution_type: str
    challenge_deactivated: bool
    display_consequences: list[ConsequenceDisplay]
