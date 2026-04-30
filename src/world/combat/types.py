"""Type definitions for the combat system."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from world.vitals.types import DamageConsequenceResult

if TYPE_CHECKING:
    from world.checks.types import CheckResult
    from world.combat.models import (
        CombatOpponent,
        CombatParticipant,
        CombatRoundAction,
        ComboDefinition,
    )
    from world.magic.types import TechniqueUseResult


@dataclass(frozen=True)
class OpponentDamageResult:
    """Result of applying damage to an NPC."""

    damage_dealt: int
    health_damaged: bool
    probed: bool
    probing_increment: int
    defeated: bool


@dataclass(frozen=True)
class ParticipantDamageResult:
    """Result of applying damage to a PC."""

    damage_dealt: int
    health_after: int
    knockout_eligible: bool
    death_eligible: bool
    permanent_wound_eligible: bool


@dataclass(frozen=True)
class ComboSlotMatch:
    """A single slot in a combo matched to a participant's action."""

    slot_number: int
    participant: CombatParticipant
    action: CombatRoundAction


@dataclass(frozen=True)
class AvailableCombo:
    """A combo whose slots are all satisfied by current round actions."""

    combo: ComboDefinition
    slot_matches: list[ComboSlotMatch]
    known_by_participant: bool


@dataclass(frozen=True)
class DefenseResult:
    """Result of a PC defending against an NPC attack."""

    success_level: int
    damage_multiplier: float
    final_damage: int
    damage_result: ParticipantDamageResult


@dataclass
class ActionOutcome:
    """Outcome of a single entity's action during resolution."""

    entity_type: str  # "pc" or "npc"
    entity_label: str
    damage_results: list[OpponentDamageResult | ParticipantDamageResult] = field(
        default_factory=list,
    )
    combo_used: ComboDefinition | None = None
    damage_consequences: list[DamageConsequenceResult] = field(default_factory=list)


@dataclass
class RoundResolutionResult:
    """Full result of resolving a combat round."""

    round_number: int
    action_outcomes: list[ActionOutcome] = field(default_factory=list)
    phase_transitions: list[tuple[CombatOpponent, int]] = field(default_factory=list)
    encounter_completed: bool = False
    available_combos: list[AvailableCombo] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Combat magic pipeline integration (Spec: 2026-04-30)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CombatTechniqueResolution:
    """Returned from a combat resolver into use_technique.

    Frozen — once the inner resolution is computed it cannot change.
    Read by the adapter to populate the outer ActionOutcome. Exposes
    check_result at the top level (no main_result wrapper) — the
    use_technique extractor accepts this shape per spec
    2026-04-30-combat-magic-pipeline-integration-design.
    """

    check_result: CheckResult
    damage_results: list[OpponentDamageResult]
    pull_flat_bonus: int
    scaled_damage: int


@dataclass(frozen=True)
class CombatTechniqueResult:
    """Adapter's return shape — what _resolve_pc_action consumes.

    Wraps the magic-pipeline outcome (TechniqueUseResult) plus the
    combat-side damage_results extracted from it. Frozen because the
    cast is over by the time this is constructed.
    """

    damage_results: list[OpponentDamageResult]
    technique_use_result: TechniqueUseResult
