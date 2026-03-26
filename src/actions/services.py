"""Service functions for action resolution."""

from __future__ import annotations

from typing import TYPE_CHECKING

from actions.constants import Pipeline, PlayerDecision, ResolutionPhase
from actions.types import (
    PendingActionResolution,
    SceneActionResult,
    StepResult,
    WeightedConsequence,
)
from world.checks.consequence_resolution import (
    apply_resolution,
    select_consequence_from_result,
)
from world.checks.services import perform_check
from world.checks.types import PendingResolution, ResolutionContext

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.models import ConsequencePool
    from actions.models.action_templates import ActionTemplate, ActionTemplateGate
    from actions.models.consequence_pools import ConsequencePoolEntry
    from world.checks.types import CheckResult
    from world.mechanics.types import AppliedEffect


def get_effective_consequences(pool: ConsequencePool) -> list[WeightedConsequence]:
    """Resolve pool inheritance into a flat list of weighted consequences.

    For pools without a parent, returns the pool's own entries.
    For child pools, starts with the parent's entries, then applies
    the child's modifications (additions, exclusions, weight overrides).
    """
    entries = list(pool.entries.select_related("consequence"))

    if pool.parent_id is None:
        return _entries_to_weighted(entries)

    # Start with parent's effective consequences
    parent_entries = list(pool.parent.entries.select_related("consequence"))
    parent_by_consequence_id: dict[int, WeightedConsequence] = {}
    for entry in parent_entries:
        if entry.is_excluded:
            continue
        wc = _entry_to_weighted(entry)
        parent_by_consequence_id[entry.consequence_id] = wc

    # Apply child modifications
    for entry in entries:
        cid = entry.consequence_id
        if entry.is_excluded:
            parent_by_consequence_id.pop(cid, None)
        elif cid in parent_by_consequence_id:
            # Override weight
            if entry.weight_override is not None:
                parent_by_consequence_id[cid] = _entry_to_weighted(entry)
        else:
            # Add new consequence
            parent_by_consequence_id[cid] = _entry_to_weighted(entry)

    return list(parent_by_consequence_id.values())


def _entries_to_weighted(
    entries: list[ConsequencePoolEntry],
) -> list[WeightedConsequence]:
    """Convert pool entries to WeightedConsequence list, skipping excluded."""
    return [_entry_to_weighted(e) for e in entries if not e.is_excluded]


def _entry_to_weighted(entry: ConsequencePoolEntry) -> WeightedConsequence:
    """Convert a single ConsequencePoolEntry to WeightedConsequence."""
    consequence = entry.consequence
    weight_override = entry.weight_override
    return WeightedConsequence(
        consequence=consequence,
        weight=weight_override if weight_override is not None else consequence.weight,
        character_loss=consequence.character_loss,
    )


# ---------------------------------------------------------------------------
# Resolution Pipeline
# ---------------------------------------------------------------------------


def start_action_resolution(
    character: ObjectDB,
    template: ActionTemplate,
    target_difficulty: int,
    context: ResolutionContext,
) -> PendingActionResolution:
    """Start an action resolution pipeline and run it to completion or pause.

    For SINGLE pipelines: runs the main check, selects and applies consequences,
    returns COMPLETE.

    For GATED pipelines: processes gates in order, then main step. May pause
    with awaiting_confirmation=True if a gate pool contains character_loss
    consequences.
    """
    pending = PendingActionResolution(
        template_id=template.pk,
        character_id=character.pk,
        target_difficulty=target_difficulty,
        resolution_context_data={
            "character_id": character.pk,
            "challenge_instance_id": (
                context.challenge_instance.pk if context.challenge_instance else None
            ),
        },
        current_phase=ResolutionPhase.GATE_PENDING,
    )

    if template.pipeline == Pipeline.GATED:
        gates = list(template.gates.order_by("step_order"))
        for gate in gates:
            # Check for dangerous consequences before running
            if gate.consequence_pool_id and _pool_has_character_loss(gate.consequence_pool):
                pending.awaiting_confirmation = True
                return pending

            gate_result = _run_gate(character, gate, target_difficulty, context)
            pending.gate_results.append(gate_result)

            gate_failed = (
                gate_result.check_result.success_level <= 0
                if gate_result.check_result.outcome
                else True
            )

            if gate_failed and gate.failure_aborts:
                pending.current_phase = ResolutionPhase.GATE_RESOLVED
                return pending

    pending.current_phase = ResolutionPhase.MAIN_PENDING
    main_result = _run_main_step(character, template, target_difficulty, context)
    pending.main_result = main_result
    pending.current_phase = ResolutionPhase.MAIN_RESOLVED

    # Context pools skipped for MVP — will integrate in Task 10
    pending.current_phase = ResolutionPhase.COMPLETE
    return pending


def advance_resolution(
    pending: PendingActionResolution,
    context: ResolutionContext,
    player_decision: str | None = None,
) -> PendingActionResolution:
    """Resume a paused pipeline after player decision.

    Called when the pipeline was paused (awaiting_confirmation or
    awaiting_intervention). Resumes from where it left off.

    Supported decisions:
      - "confirm": clear awaiting flag, continue the pipeline
      - "abort": set phase to COMPLETE, return without further resolution
      - "reroll": re-run consequence selection on the current step
    """
    from actions.models import ActionTemplate  # noqa: PLC0415

    if player_decision == PlayerDecision.ABORT:
        pending.awaiting_confirmation = False
        pending.awaiting_intervention = False
        pending.current_phase = ResolutionPhase.COMPLETE
        return pending

    if player_decision == PlayerDecision.CONFIRM and pending.awaiting_confirmation:
        pending.awaiting_confirmation = False
        template = ActionTemplate.objects.get(pk=pending.template_id)
        character = context.character

        if pending.current_phase == ResolutionPhase.GATE_PENDING:
            # Resume gate processing from where we left off
            gates = list(template.gates.order_by("step_order"))
            processed_count = len(pending.gate_results)

            for gate in gates[processed_count:]:
                gate_result = _run_gate(character, gate, pending.target_difficulty, context)
                pending.gate_results.append(gate_result)

                gate_failed = (
                    gate_result.check_result.success_level <= 0
                    if gate_result.check_result.outcome
                    else True
                )

                if gate_failed and gate.failure_aborts:
                    pending.current_phase = ResolutionPhase.GATE_RESOLVED
                    return pending

        # If gates passed (or no more gates), run main step
        if pending.main_result is None:
            pending.current_phase = ResolutionPhase.MAIN_PENDING
            main_result = _run_main_step(character, template, pending.target_difficulty, context)
            pending.main_result = main_result
            pending.current_phase = ResolutionPhase.MAIN_RESOLVED

        pending.current_phase = ResolutionPhase.COMPLETE
        return pending

    if player_decision == PlayerDecision.REROLL:
        pending.awaiting_intervention = False
        # Re-run consequence selection is a future feature placeholder
        # For now, just continue
        pending.current_phase = ResolutionPhase.COMPLETE
        return pending

    return pending


# ---------------------------------------------------------------------------
# Pipeline helper functions
# ---------------------------------------------------------------------------


def _run_gate(
    character: ObjectDB,
    gate: ActionTemplateGate,
    difficulty: int,
    context: ResolutionContext,
) -> StepResult:
    """Run a single gate check step."""
    check_result = perform_check(character, gate.check_type, difficulty)

    if gate.consequence_pool_id:
        consequences = get_effective_consequences(gate.consequence_pool)
        if consequences:
            pending_resolution = select_consequence_from_result(
                character, check_result, consequences
            )
            applied = apply_resolution(pending_resolution, context)
            return _build_step_result(f"gate:{gate.gate_role}", pending_resolution, applied)

    return _build_step_result(
        f"gate:{gate.gate_role}",
        PendingResolution(check_result=check_result, selected_consequence=None),  # type: ignore[arg-type]
        [],
    )


def _run_main_step(
    character: ObjectDB,
    template: ActionTemplate,
    difficulty: int,
    context: ResolutionContext,
) -> StepResult:
    """Run the main resolution step."""
    check_result = perform_check(character, template.check_type, difficulty)

    if template.consequence_pool is None:
        return _build_step_result(
            "main",
            PendingResolution(check_result=check_result, selected_consequence=None),  # type: ignore[arg-type]
            [],
        )

    consequences = get_effective_consequences(template.consequence_pool)

    if consequences:
        pending_resolution = select_consequence_from_result(character, check_result, consequences)
        applied = apply_resolution(pending_resolution, context)
        return _build_step_result("main", pending_resolution, applied)

    return _build_step_result(
        "main",
        PendingResolution(check_result=check_result, selected_consequence=None),  # type: ignore[arg-type]
        [],
    )


def _run_context_pools(
    character: ObjectDB,
    check_result: CheckResult,
    context: ResolutionContext,
) -> list[StepResult]:
    """Run context consequence pools based on location Properties.

    Queries ContextConsequencePool for rider pools (check_type=null) matching
    Properties on the character's location, then selects consequences using
    the main step's check result.
    """
    from world.mechanics.models import ContextConsequencePool  # noqa: PLC0415

    location = context.location
    if location is None:
        return []

    context_pools = ContextConsequencePool.objects.filter(
        property__object_properties__object=location,
        check_type__isnull=True,
    ).select_related("consequence_pool")

    results: list[StepResult] = []
    for ctx_pool in context_pools:
        consequences = get_effective_consequences(ctx_pool.consequence_pool)
        if not consequences:
            continue
        pending_resolution = select_consequence_from_result(character, check_result, consequences)
        applied = apply_resolution(pending_resolution, context)
        results.append(
            _build_step_result(
                f"context:{ctx_pool.property.name}",
                pending_resolution,
                applied,
            )
        )

    return results


def _pool_has_character_loss(pool: ConsequencePool) -> bool:
    """Check if any effective consequence in the pool has character_loss=True."""
    consequences = get_effective_consequences(pool)
    return any(wc.character_loss for wc in consequences)


def _build_step_result(
    step_label: str,
    pending_resolution: PendingResolution,
    applied_effects: list[AppliedEffect],
) -> StepResult:
    """Build a StepResult from intermediate resolution data."""
    consequence = pending_resolution.selected_consequence
    consequence_id = consequence.pk if consequence else None
    effect_ids = [
        ae.created_instance.pk
        for ae in applied_effects
        if ae.applied and ae.created_instance and hasattr(ae.created_instance, "pk")
    ]

    return StepResult(
        step_label=step_label,
        check_result=pending_resolution.check_result,
        consequence_id=consequence_id,
        applied_effect_ids=effect_ids if effect_ids else None,
    )


# ---------------------------------------------------------------------------
# Scene Action Resolution
# ---------------------------------------------------------------------------


def resolve_scene_action(
    *,
    character: ObjectDB,
    action_template: ActionTemplate | None,
    action_key: str,
    difficulty: int,
) -> SceneActionResult:
    """Resolve a scene-based action check using an ActionTemplate.

    Uses the template's check_type FK to call perform_check(). Returns
    a SceneActionResult with the check outcome.

    Args:
        character: The character performing the action.
        action_template: The ActionTemplate defining this action's check type.
        action_key: Display key for the action (used in result messages).
        difficulty: The numeric difficulty value.

    Returns:
        SceneActionResult with check outcome.
    """
    if action_template is None:
        return SceneActionResult(
            success=False,
            action_key=action_key,
            difficulty=difficulty,
            message=f"No action template for '{action_key}'.",
        )

    check_result = perform_check(
        character, action_template.check_type, target_difficulty=difficulty
    )

    return SceneActionResult(
        success=check_result.success_level > 0,
        action_key=action_key,
        difficulty=difficulty,
        message=f"{action_template.name}: {check_result.outcome_name}",
        check_outcome=check_result.outcome_name,
    )
