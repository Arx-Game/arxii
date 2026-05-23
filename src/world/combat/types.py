"""Type definitions for the combat system."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from world.vitals.types import DamageConsequenceResult

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.checks.models import Consequence
    from world.checks.types import CheckResult
    from world.combat.models import (
        Clash,
        ClashContribution,
        ClashRound,
        CombatOpponent,
        CombatParticipant,
        CombatRoundAction,
        ComboDefinition,
    )
    from world.conditions.models import ConditionTemplate
    from world.magic.models import Affinity
    from world.magic.models.techniques import Technique
    from world.magic.types import TechniqueUseResult
    from world.mechanics.types import ChallengeResolutionResult
    from world.traits.models import CheckOutcome


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
    challenge_outcomes: list[ChallengeResolutionResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Combat magic pipeline integration (Spec: 2026-04-30)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AppliedConditionResult:
    """Per-condition apply outcome from CombatTechniqueResolver._apply_conditions."""

    target: ObjectDB
    condition: ConditionTemplate
    severity_applied: int
    duration_rounds: int | None
    success: bool


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
    applied_conditions: list[AppliedConditionResult]
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
    applied_conditions: list[AppliedConditionResult]
    technique_use_result: TechniqueUseResult


# ---------------------------------------------------------------------------
# Clash pipeline types (Task 2.3)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClashContributionResult:
    """Result of a single PC's per-round clash contribution.

    Produced by ``commit_to_clash``. Captures the check outcome and all
    magic-pipeline side-effects (anima cost, Soulfray, Audere) so the
    round-resolution engine can aggregate progress without re-running the cast.

    Fields:
        character: The ``CharacterSheet`` that made this contribution — echoes
            back the ``character`` argument passed to ``commit_to_clash`` so
            the aggregator can write the ``ClashContribution`` audit row without
            re-resolving the identity.
        action_slot: The ``ClashActionSlot`` value (``"FOCUSED"`` or
            ``"PASSIVE"``) — echoes back the ``action_slot`` argument.
        technique: The ``Technique`` used for this contribution — echoes back
            the ``technique`` argument.
        check_outcome: The ``CheckOutcome`` that the contribution roll produced.
        progress_delta: Change in clash progress this contribution contributes,
            derived from ``outcome_to_delta``.
        anima_committed: The raw strain commitment (anima poured in beyond the
            effective-cost floor).
        was_overburn: ``True`` when ``technique_use_result.was_deficit`` is set —
            the cast dipped into negative anima.
        was_audere: ``True`` when the character was in Audere during the cast.
        soulfray_severity_accrued: Severity points added by Soulfray this cast
            (``soulfray_result.severity_added`` when present, else 0).
        technique_use_result: The full ``TechniqueUseResult`` from the magic
            pipeline for callers that need lower-level details.
    """

    character: CharacterSheet
    action_slot: str
    technique: Technique
    check_outcome: CheckOutcome
    progress_delta: int
    anima_committed: int
    was_overburn: bool
    was_audere: bool
    soulfray_severity_accrued: int
    technique_use_result: TechniqueUseResult


@dataclass(frozen=True)
class ClashRoundResult:
    """Result of one round of clash aggregation.

    Produced by ``aggregate_clash_round``. Carries the persisted DB rows and
    the numeric values that drove the meter update so the caller can surface
    feedback to players without re-querying.

    Fields:
        clash_round: The persisted ``ClashRound`` row written this round.
        contributions: The persisted ``ClashContribution`` rows — one per PC
            contribution passed in.
        pc_delta_sum: The raw sum of all PC contribution deltas this round.
        npc_delta: The NPC push magnitude (non-negative) passed in by the caller.
        progress_after: The updated ``clash.progress`` value after this round.
    """

    clash_round: ClashRound
    contributions: list[ClashContribution]
    pc_delta_sum: int
    npc_delta: int
    progress_after: int


# ---------------------------------------------------------------------------
# Clash resolution types (Task 4.2)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClashResolutionResult:
    """Result of clash resolution.

    Produced by ``resolve_clash``. Carries the resolved Clash row, the tier
    that triggered resolution, and the consequence (if any) drawn from the
    resolution pool.

    Fields:
        clash: The resolved ``Clash`` instance (status=RESOLVED,
            resolution and resolved_round set).
        resolution: The ``ClashResolution`` tier — echoed for caller
            convenience so the round driver need not re-read the model field.
        consequence_applied: The ``Consequence`` selected from the resolution
            pool, or ``None`` when the pool had no matching tier entry.
    """

    clash: Clash
    resolution: str  # ClashResolution value — str to avoid circular import at runtime
    consequence_applied: Consequence | None


# ---------------------------------------------------------------------------
# Clash round driver types (Task 5.2)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PreparedClashContribution:
    """One PC's prepared input to ``run_clash_round``.

    Bundles everything the round driver needs to call ``commit_to_clash``
    for a single PC participant and compute the affinity tilt for that
    participant's technique against the NPC's attack affinity.

    Fields:
        character_sheet: The ``CharacterSheet`` of the PC making this
            contribution.
        action_slot: ``ClashActionSlot`` value (``"FOCUSED"`` or
            ``"PASSIVE"``).
        technique: The ``Technique`` the PC is using for this contribution.
        strain_commitment: Extra anima committed on top of the technique's
            effective cost floor.
        npc_attack_affinity: The ``Affinity`` of the NPC's attack (for the
            affinity tilt computation), or ``None`` for non-magical attacks.
    """

    character_sheet: CharacterSheet
    action_slot: str
    technique: Technique
    strain_commitment: int
    npc_attack_affinity: Affinity | None
