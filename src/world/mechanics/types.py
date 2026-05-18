"""
Mechanics System Types

Dataclasses and type definitions for the mechanics service layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from actions.models.action_templates import ActionTemplate
    from world.checks.models import CheckType, Consequence
    from world.checks.types import CheckResult
    from world.mechanics.models import ChallengeApproach, ChallengeInstance

from world.checks.types import OutcomeDisplay
from world.mechanics.constants import CapabilitySourceType, DifficultyIndicator
from world.mechanics.models import Prerequisite

# Re-export for backwards compatibility within mechanics app
ConsequenceDisplay = OutcomeDisplay


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
class PrerequisiteEvaluation:
    """Result of evaluating a Prerequisite against game state."""

    met: bool
    reason: str = ""


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
    prerequisite: Prerequisite | None = None


@dataclass
class AvailableAction:
    """An Action available to a character for a specific Challenge.

    ``resolved_check_type`` and ``resolved_action_template`` carry the already-loaded
    model instances (populated from the prefetched ChallengeApproach by
    ``_match_approaches``).  They are excluded from the ``AvailableActionSerializer``
    because DataclassSerializer cannot render arbitrary model instances — callers in
    ``actions.player_interface`` read them directly.  ``check_type_name`` is kept for
    backwards-compatibility with existing serializer consumers.
    """

    application_id: int
    application_name: str
    capability_source: CapabilitySource
    challenge_instance_id: int
    challenge_name: str
    approach_id: int | None
    check_type_name: str
    display_name: str
    custom_description: str
    difficulty_indicator: DifficultyIndicator | None = None
    prerequisite_met: bool = True
    prerequisite_reasons: list[str] = field(default_factory=list)
    # Resolved model instances (populated from already-prefetched approach data).
    # Default None so existing construction sites that don't pass these still work.
    resolved_check_type: CheckType | None = field(default=None)
    resolved_action_template: ActionTemplate | None = field(default=None)
    # Challenge/approach instances for dispatch — populated from already-loaded prefetch
    # data in _match_approaches (no additional query).  Excluded from wire serialization.
    resolved_challenge_instance: ChallengeInstance | None = field(default=None)
    resolved_challenge_approach: ChallengeApproach | None = field(default=None)


@dataclass
class ChallengeGroup:
    """Available actions grouped by challenge for API response."""

    challenge_instance_id: int
    challenge_name: str
    actions: list[AvailableAction]


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
    created_instance: Any | None = None  # optional ref for caller bookkeeping


@dataclass
class ChallengeResolutionResult:
    """Full result from resolve_challenge()."""

    challenge_instance_id: int
    challenge_name: str
    approach_name: str
    check_result: CheckResult
    consequence: Consequence
    applied_effects: list[AppliedEffect]
    resolution_type: str
    challenge_deactivated: bool
    display_consequences: list[OutcomeDisplay]
