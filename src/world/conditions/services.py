"""
Condition Service Layer

Provides the interface for applying, removing, and querying conditions on targets.
Handles all interaction processing, modifier calculations, and round-based updates.

Design principles:
- Everything is math (no binary immunity)
- Intensity - Resistance = Net Value
- Bidirectional modifiers (conditions can be good or bad depending on context)
"""

from dataclasses import dataclass, field
from datetime import timedelta
from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import Q, QuerySet, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from flows.constants import EventName
from flows.emit import emit_event
from flows.events.payloads import (
    ConditionAppliedPayload,
    ConditionPreApplyPayload,
    ConditionRemovedPayload,
    ConditionStageChangedPayload,
)
from world.checks.models import CheckType
from world.conditions.constants import (
    ConditionInteractionOutcome,
    ConditionInteractionTrigger,
    DamageTickTiming,
    DurationType,
    StackBehavior,
)
from world.conditions.models import (
    CapabilityType,
    ConditionCapabilityEffect,
    ConditionCheckModifier,
    ConditionConditionInteraction,
    ConditionDamageInteraction,
    ConditionDamageOverTime,
    ConditionInstance,
    ConditionResistanceModifier,
    ConditionStage,
    ConditionTemplate,
    DamageType,
)
from world.conditions.types import (
    ApplyConditionResult,
    CapabilityStatus,
    CheckModifierResult,
    DamageInteractionResult,
    DecayTickSummary,
    InteractionResult,
    ResistanceModifierResult,
    RoundTickResult,
    SeverityAdvanceResult,
    SeverityDecayResult,
)
from world.game_clock.services import get_ic_now
from world.mechanics.models import CharacterModifier

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.conditions.models import ConditionCategory
    from world.magic.models import Technique

# Timing constants
SECONDS_PER_ROUND = 6


# =============================================================================
# Core Service Functions
# =============================================================================


def get_active_conditions(
    target: "ObjectDB",
    *,
    category: "ConditionCategory | None" = None,
    condition: ConditionTemplate | None = None,
    include_suppressed: bool = False,
) -> QuerySet[ConditionInstance]:
    """
    Get active condition instances on a target.

    Args:
        target: The ObjectDB instance to query
        category: Filter to specific category instance
        condition: Filter to specific condition template instance
        include_suppressed: Include suppressed conditions

    Returns:
        QuerySet of active ConditionInstance objects
    """
    qs = ConditionInstance.objects.filter(target=target).select_related(
        "condition",
        "condition__category",
        "current_stage",
    )

    if not include_suppressed:
        qs = qs.filter(
            Q(is_suppressed=False)
            | Q(suppressed_until__isnull=False, suppressed_until__lt=timezone.now())
        )

    if category:
        qs = qs.filter(condition__category=category)

    if condition:
        qs = qs.filter(condition=condition)

    return qs


def has_condition(
    target: "ObjectDB",
    condition: ConditionTemplate,
    *,
    include_suppressed: bool = False,
) -> bool:
    """
    Check if target has a specific condition.

    Args:
        target: The ObjectDB instance
        condition: ConditionTemplate instance
        include_suppressed: Count suppressed conditions

    Returns:
        True if condition is present
    """
    return get_active_conditions(
        target, condition=condition, include_suppressed=include_suppressed
    ).exists()


def get_condition_instance(
    target: "ObjectDB",
    condition: ConditionTemplate,
    *,
    include_suppressed: bool = False,
) -> ConditionInstance | None:
    """
    Get a specific condition instance on a target.

    Args:
        target: The ObjectDB instance
        condition: ConditionTemplate instance
        include_suppressed: Include suppressed conditions in search

    Returns:
        ConditionInstance or None
    """
    return get_active_conditions(
        target, condition=condition, include_suppressed=include_suppressed
    ).first()


@dataclass
class _ApplyConditionParams:
    """Parameters for applying a condition (reduces argument count)."""

    target: "ObjectDB"
    severity: int = 1
    duration_rounds: int | None = None
    source_character: "ObjectDB | None" = None
    source_technique: "Technique | None" = None
    source_description: str = ""


@dataclass
class _BulkConditionContext:
    """Pre-fetched data for bulk condition application.

    Holds all DB-fetched state needed by _apply_single, avoiding per-call queries.
    """

    # target_id -> list of active ConditionInstance
    active_instances_by_target: dict[int, list[ConditionInstance]] = field(default_factory=dict)
    # (target_id, condition_id) -> ConditionInstance or None
    existing_pairs: dict[tuple[int, int], ConditionInstance] = field(default_factory=dict)
    # All prevention interactions for the template set
    prevention_interactions: list[ConditionConditionInteraction] = field(default_factory=list)
    # All application interactions for the template set
    application_interactions: list[ConditionConditionInteraction] = field(default_factory=list)
    # condition_id -> first ConditionStage (for progressive templates)
    first_stages: dict[int, ConditionStage] = field(default_factory=dict)

    def get_existing_instance(
        self,
        target_id: int,
        condition_id: int,
    ) -> ConditionInstance | None:
        return self.existing_pairs.get((target_id, condition_id))

    def get_active_condition_ids(self, target_id: int) -> set[int]:
        return {i.condition_id for i in self.active_instances_by_target.get(target_id, [])}


def _build_bulk_context(
    targets: list["ObjectDB"],
    templates: list[ConditionTemplate],
) -> _BulkConditionContext:
    """Batch-fetch all data needed for applying conditions to multiple targets.

    One query per data type instead of per (target, condition) pair.
    """
    target_ids = [t.pk for t in targets]
    template_ids = [t.pk for t in templates]

    # Suppression filter matching get_active_conditions() default behavior
    not_suppressed = Q(is_suppressed=False) | Q(
        suppressed_until__isnull=False,
        suppressed_until__lt=timezone.now(),
    )

    # 1. All active (non-suppressed) condition instances for all targets (1 query)
    all_instances = list(
        ConditionInstance.objects.filter(
            not_suppressed,
            target_id__in=target_ids,
        ).select_related("condition", "condition__category", "current_stage")
    )

    active_by_target: dict[int, list[ConditionInstance]] = {}
    for inst in all_instances:
        active_by_target.setdefault(inst.target_id, []).append(inst)

    # 2. Build existing pairs from all_instances (no extra query — m3 fix)
    existing_pairs: dict[tuple[int, int], ConditionInstance] = {
        (inst.target_id, inst.condition_id): inst
        for inst in all_instances
        if inst.condition_id in template_ids
    }

    # 3. All prevention interactions involving these templates (1 query with Q OR)
    # Include template_ids so intra-batch template interactions are detected
    all_condition_ids = {i.condition_id for i in all_instances} | set(template_ids)
    prevention_interactions = list(
        ConditionConditionInteraction.objects.filter(
            Q(
                condition_id__in=all_condition_ids,
                other_condition_id__in=template_ids,
                trigger=ConditionInteractionTrigger.ON_OTHER_APPLIED,
                outcome=ConditionInteractionOutcome.PREVENT_OTHER,
            )
            | Q(
                condition_id__in=template_ids,
                other_condition_id__in=all_condition_ids,
                trigger=ConditionInteractionTrigger.ON_SELF_APPLIED,
                outcome=ConditionInteractionOutcome.PREVENT_SELF,
            )
        )
        .select_related("condition", "other_condition")
        .order_by("-priority")
    )

    # 4. All application interactions involving these templates (1 query)
    application_interactions = list(
        ConditionConditionInteraction.objects.filter(
            Q(
                condition_id__in=template_ids,
                other_condition_id__in=all_condition_ids,
                trigger=ConditionInteractionTrigger.ON_SELF_APPLIED,
            )
            | Q(
                condition_id__in=all_condition_ids,
                other_condition_id__in=template_ids,
                trigger=ConditionInteractionTrigger.ON_OTHER_APPLIED,
            )
        )
        .select_related("condition", "other_condition")
        .order_by("-priority")
    )

    # 5. First stages for progressive templates (1 query, PG DISTINCT ON)
    progressive_ids = [t.pk for t in templates if t.has_progression]
    first_stages: dict[int, ConditionStage] = {}
    if progressive_ids:
        for stage in (
            ConditionStage.objects.filter(condition_id__in=progressive_ids)
            .order_by("condition_id", "stage_order")
            .distinct("condition_id")
        ):
            first_stages[stage.condition_id] = stage

    return _BulkConditionContext(
        active_instances_by_target=active_by_target,
        existing_pairs=existing_pairs,
        prevention_interactions=prevention_interactions,
        application_interactions=application_interactions,
        first_stages=first_stages,
    )


def _check_prevention_from_context(
    target_id: int,
    incoming_condition: ConditionTemplate,
    ctx: _BulkConditionContext,
) -> ConditionTemplate | None:
    """Check prevention using pre-fetched interactions."""
    active_condition_ids = ctx.get_active_condition_ids(target_id)
    for interaction in ctx.prevention_interactions:
        # Check "existing prevents incoming"
        if (
            interaction.other_condition_id == incoming_condition.pk
            and interaction.condition_id in active_condition_ids
            and interaction.trigger == ConditionInteractionTrigger.ON_OTHER_APPLIED
            and interaction.outcome == ConditionInteractionOutcome.PREVENT_OTHER
        ):
            return interaction.condition
        # Check "incoming self-prevents"
        if (
            interaction.condition_id == incoming_condition.pk
            and interaction.other_condition_id in active_condition_ids
            and interaction.trigger == ConditionInteractionTrigger.ON_SELF_APPLIED
            and interaction.outcome == ConditionInteractionOutcome.PREVENT_SELF
        ):
            return interaction.other_condition
    return None


def _process_interactions_from_context(
    target_id: int,
    incoming_condition: ConditionTemplate,
    ctx: _BulkConditionContext,
) -> InteractionResult:
    """Process application interactions using pre-fetched data.

    Mutates ctx.active_instances_by_target in-place so subsequent
    iterations in bulk_apply_conditions see removals from earlier iterations.
    """
    result = InteractionResult()
    active_instances = ctx.active_instances_by_target.get(target_id, [])
    active_condition_ids = {i.condition_id for i in active_instances}

    for interaction in ctx.application_interactions:
        # Filter to interactions relevant to this target's active conditions
        if interaction.condition_id == incoming_condition.pk:
            if interaction.other_condition_id not in active_condition_ids:
                continue
            match_id = interaction.other_condition_id
        elif interaction.other_condition_id == incoming_condition.pk:
            if interaction.condition_id not in active_condition_ids:
                continue
            match_id = interaction.condition_id
        else:
            continue

        existing_instance = next(
            (i for i in active_instances if i.condition_id == match_id),
            None,
        )
        if not existing_instance:
            continue

        if _should_remove_existing(interaction, incoming_condition):
            result.removed.append(existing_instance.condition)
            existing_instance.delete()
            active_instances.remove(existing_instance)
            active_condition_ids.discard(match_id)
            # Clean existing_pairs so later batch entries don't resurrect it
            ctx.existing_pairs.pop(
                (existing_instance.target_id, match_id),
                None,
            )

    return result


def _create_instance_from_context(
    template: ConditionTemplate,
    params: _ApplyConditionParams,
    interaction_results: InteractionResult,
    ctx: _BulkConditionContext,
) -> ApplyConditionResult:
    """Create a new condition instance using pre-fetched stage data."""
    rounds = params.duration_rounds or template.default_duration_value
    rounds_remaining = rounds if template.default_duration_type == DurationType.ROUNDS else None

    first_stage = ctx.first_stages.get(template.pk) if template.has_progression else None
    stage_rounds = (
        first_stage.rounds_to_next
        if first_stage and first_stage.rounds_to_next is not None
        else None
    )

    instance = ConditionInstance.objects.create(
        target=params.target,
        condition=template,
        severity=params.severity,
        stacks=1,
        rounds_remaining=rounds_remaining,
        current_stage=first_stage,
        stage_rounds_remaining=stage_rounds,
        source_character=params.source_character,
        source_technique=params.source_technique,
        source_description=params.source_description,
    )

    return ApplyConditionResult(
        success=True,
        instance=instance,
        stacks_added=1,
        message=f"{template.name} applied",
        removed_conditions=interaction_results.removed,
        applied_conditions=interaction_results.applied,
    )


def _apply_single(
    target: "ObjectDB",
    template: ConditionTemplate,
    params: _ApplyConditionParams,
    ctx: _BulkConditionContext,
) -> ApplyConditionResult:
    """Apply a single condition using pre-fetched context data.

    Core logic extracted from apply_condition. All DB reads come from ctx;
    only writes (create/save/delete) hit the database.
    """
    prevention = _check_prevention_from_context(target.pk, template, ctx)
    if prevention:
        return ApplyConditionResult(
            success=False,
            was_prevented=True,
            prevented_by=prevention,
            message=f"{template.name} was prevented by {prevention.name}",
        )

    interaction_results = _process_interactions_from_context(target.pk, template, ctx)

    existing = ctx.get_existing_instance(target.pk, template.pk)

    if existing:
        if template.is_stackable and existing.stacks < template.max_stacks:
            return _handle_stacking(existing, template, params, interaction_results)
        return _handle_refresh(existing, template, params, interaction_results)

    apply_result = _create_instance_from_context(
        template,
        params,
        interaction_results,
        ctx,
    )

    # Update context so subsequent bulk iterations see this new instance
    if apply_result.instance:
        new_inst = apply_result.instance
        ctx.existing_pairs[(target.pk, template.pk)] = new_inst
        ctx.active_instances_by_target.setdefault(target.pk, []).append(
            new_inst,
        )

    return apply_result


def _handle_stacking(
    existing: ConditionInstance,
    template: ConditionTemplate,
    params: _ApplyConditionParams,
    interaction_results: InteractionResult,
) -> ApplyConditionResult:
    """Handle stacking for an existing condition instance."""
    existing.stacks += 1

    if template.stack_behavior in (
        StackBehavior.INTENSITY,
        StackBehavior.BOTH,
    ):
        existing.severity = max(existing.severity, params.severity)

    if template.stack_behavior in (
        StackBehavior.DURATION,
        StackBehavior.BOTH,
    ):
        rounds = params.duration_rounds or template.default_duration_value
        if existing.rounds_remaining is not None:
            existing.rounds_remaining += rounds

    existing.save()

    return ApplyConditionResult(
        success=True,
        instance=existing,
        stacks_added=1,
        message=f"{template.name} stacked to {existing.stacks}",
        removed_conditions=interaction_results.removed,
        applied_conditions=interaction_results.applied,
    )


def _handle_refresh(
    existing: ConditionInstance,
    template: ConditionTemplate,
    params: _ApplyConditionParams,
    interaction_results: InteractionResult,
) -> ApplyConditionResult:
    """Handle refresh for a non-stackable existing condition."""
    if params.severity < existing.severity:
        return ApplyConditionResult(
            success=True,
            instance=existing,
            message=f"{template.name} already active at higher severity",
            removed_conditions=interaction_results.removed,
            applied_conditions=interaction_results.applied,
        )

    existing.severity = params.severity
    rounds = params.duration_rounds or template.default_duration_value
    if template.default_duration_type == DurationType.ROUNDS:
        existing.rounds_remaining = rounds
    existing.save()

    return ApplyConditionResult(
        success=True,
        instance=existing,
        message=f"{template.name} refreshed",
        removed_conditions=interaction_results.removed,
        applied_conditions=interaction_results.applied,
    )


@transaction.atomic
def apply_condition(  # noqa: PLR0913
    target: "ObjectDB",
    condition: ConditionTemplate,
    *,
    severity: int = 1,
    duration_rounds: int | None = None,
    source_character: "ObjectDB | None" = None,
    source_technique: "Technique | None" = None,
    source_description: str = "",
) -> ApplyConditionResult:
    """Apply a condition to a target, handling stacking and interactions.

    Thin wrapper around _apply_single — builds a single-item context
    and delegates. For applying multiple conditions, use bulk_apply_conditions.

    Emits reactive events:
    - CONDITION_PRE_APPLY (cancellable)
    - CONDITION_APPLIED (post-save, frozen)
    """
    source = source_character or source_technique
    target_location = getattr(target, "location", None)  # noqa: GETATTR_LITERAL
    pre_payload = ConditionPreApplyPayload(
        target=target,
        template=condition,
        source=source,
        stage=None,
    )
    if target_location is not None:
        stack = emit_event(
            EventName.CONDITION_PRE_APPLY,
            pre_payload,
            location=target_location,
        )
        if stack.was_cancelled():
            return ApplyConditionResult(
                success=False,
                instance=None,
                message="cancelled by trigger",
                removed_conditions=[],
                applied_conditions=[],
            )

    ctx = _build_bulk_context([target], [condition])
    params = _ApplyConditionParams(
        target=target,
        severity=severity,
        duration_rounds=duration_rounds,
        source_character=source_character,
        source_technique=source_technique,
        source_description=source_description,
    )
    result = _apply_single(target, condition, params, ctx)

    if result.instance is not None and target_location is not None:
        emit_event(
            EventName.CONDITION_APPLIED,
            ConditionAppliedPayload(
                target=target,
                instance=result.instance,
                stage=result.instance.current_stage,
            ),
            location=target_location,
        )

    return result


@transaction.atomic
def bulk_apply_conditions(  # noqa: PLR0913
    applications: list[tuple["ObjectDB", ConditionTemplate]],
    *,
    severity: int = 1,
    duration_rounds: int | None = None,
    source_character: "ObjectDB | None" = None,
    source_technique: "Technique | None" = None,
    source_description: str = "",
) -> list[ApplyConditionResult]:
    """Apply multiple conditions in a single transaction with batched queries.

    Fetches all needed data (active instances, interactions, stages) in ~5
    queries regardless of how many (target, condition) pairs are passed.
    Each application still respects prevention, interaction, and stacking rules.
    """
    if not applications:
        return []

    targets = list({target for target, _ in applications})
    templates = list({template for _, template in applications})

    ctx = _build_bulk_context(targets, templates)

    results: list[ApplyConditionResult] = []
    for target, template in applications:
        source = source_character or source_technique
        target_location = getattr(target, "location", None)  # noqa: GETATTR_LITERAL
        pre_payload = ConditionPreApplyPayload(
            target=target,
            template=template,
            source=source,
            stage=None,
        )
        if target_location is not None:
            stack = emit_event(
                EventName.CONDITION_PRE_APPLY,
                pre_payload,
                location=target_location,
            )
            if stack.was_cancelled():
                results.append(
                    ApplyConditionResult(
                        success=False,
                        instance=None,
                        message="cancelled by trigger",
                        removed_conditions=[],
                        applied_conditions=[],
                    )
                )
                continue

        params = _ApplyConditionParams(
            target=target,
            severity=severity,
            duration_rounds=duration_rounds,
            source_character=source_character,
            source_technique=source_technique,
            source_description=source_description,
        )
        result = _apply_single(target, template, params, ctx)

        if result.instance is not None and target_location is not None:
            emit_event(
                EventName.CONDITION_APPLIED,
                ConditionAppliedPayload(
                    target=target,
                    instance=result.instance,
                    stage=result.instance.current_stage,
                ),
                location=target_location,
            )

        results.append(result)

    return results


@transaction.atomic
def remove_condition(
    target: "ObjectDB",
    condition: ConditionTemplate,
    *,
    remove_all_stacks: bool = True,
) -> bool:
    """
    Remove a condition from a target.

    Args:
        target: The ObjectDB instance
        condition: ConditionTemplate instance
        remove_all_stacks: If False, only remove one stack

    Returns:
        True if condition was removed

    Emits reactive events:
    - CONDITION_REMOVED (post-delete, frozen)
    """
    instance = get_condition_instance(target, condition)
    if not instance:
        return False

    instance_pk = instance.pk
    source = instance.source_character or instance.source_technique
    target_location = getattr(target, "location", None)  # noqa: GETATTR_LITERAL

    if not remove_all_stacks and instance.stacks > 1:
        instance.stacks -= 1
        instance.save()
        if target_location is not None:
            emit_event(
                EventName.CONDITION_REMOVED,
                ConditionRemovedPayload(
                    target=target,
                    instance_id=instance_pk,
                    template=condition,
                    source=source,
                ),
                location=target_location,
            )
        return True

    instance.delete()
    if target_location is not None:
        emit_event(
            EventName.CONDITION_REMOVED,
            ConditionRemovedPayload(
                target=target,
                instance_id=instance_pk,
                template=condition,
                source=source,
            ),
            location=target_location,
        )
    return True


@transaction.atomic
def remove_conditions_by_category(
    target: "ObjectDB",
    category: "ConditionCategory",
) -> list[ConditionTemplate]:
    """
    Remove all conditions in a category from a target.

    Args:
        target: The ObjectDB instance
        category: ConditionCategory instance to remove

    Returns:
        List of removed ConditionTemplates
    """
    instances = get_active_conditions(target, category=category)
    removed = [i.condition for i in instances]
    instances.delete()
    return removed


# =============================================================================
# Interaction Processing
# =============================================================================


def _should_remove_existing(
    interaction: ConditionConditionInteraction,
    incoming_condition: ConditionTemplate,
) -> bool:
    """Determine if an interaction should remove the existing condition."""
    outcome = interaction.outcome
    is_existing_owner = interaction.condition != incoming_condition

    if outcome == ConditionInteractionOutcome.REMOVE_SELF:
        # Remove self = existing condition removes itself when it reacts
        return is_existing_owner

    if outcome == ConditionInteractionOutcome.REMOVE_OTHER:
        # Remove other = incoming's interaction removes the existing
        return not is_existing_owner

    if outcome in (
        ConditionInteractionOutcome.REMOVE_BOTH,
        ConditionInteractionOutcome.MERGE,
    ):
        # These always remove the existing condition
        return True

    return False


@transaction.atomic
def process_damage_interactions(
    target: "ObjectDB",
    damage_type: DamageType,
) -> DamageInteractionResult:
    """
    Process condition interactions when target takes damage.

    Args:
        target: The ObjectDB taking damage
        damage_type: DamageType instance

    Returns:
        DamageInteractionResult with modifier percent and condition changes.
        Caller applies the modifier to their damage calculation.
    """
    dtype = damage_type

    result = DamageInteractionResult(
        damage_modifier_percent=0,
        removed_conditions=[],
        applied_conditions=[],
    )

    # Get all damage interactions for active conditions
    active_instances = list(get_active_conditions(target))
    condition_ids = [i.condition_id for i in active_instances]

    interactions = ConditionDamageInteraction.objects.filter(
        condition_id__in=condition_ids,
        damage_type=dtype,
    ).select_related("condition", "applies_condition")

    instance_map = {i.condition_id: i for i in active_instances}

    for interaction in interactions:
        instance = instance_map.get(interaction.condition_id)
        if not instance:
            continue

        # Accumulate damage modifier
        result.damage_modifier_percent += interaction.damage_modifier_percent

        # Handle condition removal
        if interaction.removes_condition:
            result.removed_conditions.append(instance)
            instance.delete()
            del instance_map[interaction.condition_id]

        # Handle applying new condition
        if interaction.applies_condition:
            apply_result = apply_condition(
                target,
                interaction.applies_condition,
                severity=interaction.applied_condition_severity,
                source_description=f"Triggered by {dtype.name} damage",
            )
            if apply_result.success and apply_result.instance:
                result.applied_conditions.append(apply_result.instance)

    return result


# =============================================================================
# Modifier Queries
# =============================================================================


def get_capability_status(
    target: "ObjectDB",
    capability: CapabilityType,
) -> CapabilityStatus:
    """
    Get the status of a capability for a target based on active conditions.

    Collects additive values from all active ConditionCapabilityEffect rows
    that target this capability. Floor at 0.

    Args:
        target: The ObjectDB instance
        capability: CapabilityType instance

    Returns:
        CapabilityStatus with total value and per-condition breakdown
    """
    result = CapabilityStatus()

    active_instances = get_active_conditions(target)

    for instance in active_instances:
        query = Q(condition=instance.condition)
        if instance.current_stage:
            query |= Q(stage=instance.current_stage)
        effects = ConditionCapabilityEffect.objects.filter(query, capability=capability)

        for effect in effects:
            modifier = effect.value
            if instance.current_stage:
                modifier = int(modifier * instance.current_stage.severity_multiplier)
            result.value += modifier
            result.condition_contributions.append((instance, modifier))

    # Floor at 0
    result.value = max(0, result.value)

    return result


def get_capability_value(
    target: "ObjectDB",
    capability: CapabilityType,
) -> int:
    """
    Get the total value of a capability for a character.

    Convenience wrapper around get_capability_status that returns just the value.
    Floor at 0.

    Args:
        target: The ObjectDB instance
        capability: CapabilityType instance

    Returns:
        Integer capability value (0 = effectively blocked / not possessed)
    """
    return get_capability_status(target, capability).value


def get_all_capability_values(target: "ObjectDB") -> dict[int, int]:
    """
    Get all capability values for a character.

    Batch-queries all ConditionCapabilityEffect rows for active conditions
    and aggregates per capability. Used by the obstacle system and
    capability source aggregation.

    Args:
        target: The ObjectDB instance

    Returns:
        Dict mapping capability PK to total values (floor 0)
    """
    active_instances = list(get_active_conditions(target))
    if not active_instances:
        return {}

    # Build batch filter
    condition_ids = [i.condition_id for i in active_instances]
    query = Q(condition_id__in=condition_ids)
    stage_ids = [i.current_stage_id for i in active_instances if i.current_stage_id]
    if stage_ids:
        query |= Q(stage_id__in=stage_ids)

    effects = ConditionCapabilityEffect.objects.filter(query).select_related("capability")

    # Build instance lookup maps
    instance_by_condition: dict[int, ConditionInstance] = {
        i.condition_id: i for i in active_instances
    }
    instance_by_stage: dict[int, ConditionInstance] = {
        i.current_stage_id: i for i in active_instances if i.current_stage_id
    }

    # Aggregate
    totals: dict[int, int] = {}
    for effect in effects:
        instance = instance_by_condition.get(effect.condition_id) or instance_by_stage.get(
            effect.stage_id
        )
        if not instance:
            continue

        modifier = effect.value
        if instance.current_stage:
            modifier = int(modifier * instance.current_stage.severity_multiplier)

        cap_id = effect.capability_id
        totals[cap_id] = totals.get(cap_id, 0) + modifier

    # Floor at 0
    return {cap_id: max(0, val) for cap_id, val in totals.items()}


def get_check_modifier(
    target: "ObjectDB",
    check_type: CheckType,
) -> CheckModifierResult:
    """
    Get the total modifier for a check type from active conditions.

    Args:
        target: The ObjectDB instance
        check_type: CheckType instance

    Returns:
        CheckModifierResult with total and breakdown
    """
    ctype = check_type

    result = CheckModifierResult(total_modifier=0, breakdown=[])

    active_instances = get_active_conditions(target)

    for instance in active_instances:
        # Get modifiers: condition-level OR stage-specific (if at a stage)
        query = Q(condition=instance.condition)
        if instance.current_stage:
            query |= Q(stage=instance.current_stage)
        modifiers = ConditionCheckModifier.objects.filter(query, check_type=ctype)

        for mod in modifiers:
            modifier_value = mod.modifier_value

            # Scale by severity if configured
            if mod.scales_with_severity:
                modifier_value = modifier_value * instance.effective_severity

            # Apply stage multiplier
            if instance.current_stage:
                modifier_value = int(modifier_value * instance.current_stage.severity_multiplier)

            result.total_modifier += modifier_value
            result.breakdown.append((instance, modifier_value))

    return result


def get_resistance_modifier(
    target: "ObjectDB",
    damage_type: DamageType | None = None,
) -> ResistanceModifierResult:
    """
    Get the total resistance modifier for a damage type from active conditions.

    Args:
        target: The ObjectDB instance
        damage_type: DamageType instance, or None for "all damage" modifiers only

    Returns:
        ResistanceModifierResult with total and breakdown
    """
    dtype = damage_type

    result = ResistanceModifierResult(total_modifier=0, breakdown=[])

    active_instances = get_active_conditions(target)

    for instance in active_instances:
        # Get modifiers: condition-level OR stage-specific (if at a stage)
        query = Q(condition=instance.condition)
        if instance.current_stage:
            query |= Q(stage=instance.current_stage)
        modifiers = ConditionResistanceModifier.objects.filter(query)

        if dtype:
            modifiers = modifiers.filter(Q(damage_type=dtype) | Q(damage_type__isnull=True))
        else:
            modifiers = modifiers.filter(damage_type__isnull=True)

        for mod in modifiers:
            modifier_value = mod.modifier_value

            # Apply stage multiplier
            if instance.current_stage:
                modifier_value = int(modifier_value * instance.current_stage.severity_multiplier)

            result.total_modifier += modifier_value
            result.breakdown.append((instance, modifier_value))

    return result


# =============================================================================
# Round Processing
# =============================================================================


@transaction.atomic
def process_round_start(target: "ObjectDB") -> RoundTickResult:
    """
    Process start-of-round effects for all conditions on a target.

    Args:
        target: The ObjectDB instance

    Returns:
        RoundTickResult with damage, progressions, and expirations
    """
    return _process_round_tick(target, DamageTickTiming.START_OF_ROUND)


@transaction.atomic
def process_round_end(target: "ObjectDB") -> RoundTickResult:
    """
    Process end-of-round effects for all conditions on a target.

    This also handles duration countdown and progression.

    Args:
        target: The ObjectDB instance

    Returns:
        RoundTickResult with damage, progressions, and expirations
    """
    result = _process_round_tick(target, DamageTickTiming.END_OF_ROUND)

    # Process duration countdown and progression
    _process_duration_and_progression(target, result)

    return result


@transaction.atomic
def process_action_tick(target: "ObjectDB") -> RoundTickResult:
    """
    Process on-action damage for conditions (when target takes an action).

    Args:
        target: The ObjectDB instance

    Returns:
        RoundTickResult with damage dealt
    """
    return _process_round_tick(target, DamageTickTiming.ON_ACTION)


def _process_round_tick(
    target: "ObjectDB",
    timing: DamageTickTiming,
) -> RoundTickResult:
    """
    Process damage-over-time for a specific tick timing.
    """
    result = RoundTickResult(
        damage_dealt=[],
        progressed_conditions=[],
        expired_conditions=[],
        removed_conditions=[],
    )

    active_instances = get_active_conditions(target)

    for instance in active_instances:
        # Get DoT effects: condition-level OR stage-specific (if at a stage)
        query = Q(condition=instance.condition)
        if instance.current_stage:
            query |= Q(stage=instance.current_stage)
        dot_effects = ConditionDamageOverTime.objects.filter(query, tick_timing=timing)

        for dot in dot_effects:
            damage = dot.base_damage

            # Scale by severity
            if dot.scales_with_severity:
                damage = damage * instance.effective_severity

            # Scale by stacks
            if dot.scales_with_stacks:
                damage = damage * instance.stacks

            # Apply stage multiplier
            if instance.current_stage:
                damage = int(damage * instance.current_stage.severity_multiplier)

            if damage > 0:
                result.damage_dealt.append((dot.damage_type, damage))

    return result


def _process_duration_and_progression(
    target: "ObjectDB",
    result: RoundTickResult,
) -> None:
    """
    Process duration countdown and stage progression at end of round.
    """
    active_instances = list(get_active_conditions(target))

    for instance in active_instances:
        # Duration countdown
        if instance.rounds_remaining is not None:
            instance.rounds_remaining -= 1
            if instance.rounds_remaining <= 0:
                result.expired_conditions.append(instance)
                instance.delete()
                continue

        # Stage progression
        if instance.stage_rounds_remaining is not None:
            instance.stage_rounds_remaining -= 1
            if instance.stage_rounds_remaining <= 0:
                # Progress to next stage
                next_stage = _get_next_stage(instance)
                if next_stage:
                    instance.current_stage = next_stage
                    instance.stage_rounds_remaining = next_stage.rounds_to_next
                    result.progressed_conditions.append(instance)
                else:
                    # No next stage - condition may end or stay at final stage
                    instance.stage_rounds_remaining = None

        instance.save()


def _get_next_stage(instance: ConditionInstance) -> ConditionStage | None:
    """Get the next stage for a progressive condition."""
    if not instance.current_stage:
        return None

    return (
        ConditionStage.objects.filter(
            condition=instance.condition,
            stage_order__gt=instance.current_stage.stage_order,
        )
        .order_by("stage_order")
        .first()
    )


# =============================================================================
# Utility Functions
# =============================================================================


def suppress_condition(
    target: "ObjectDB",
    condition: ConditionTemplate,
    *,
    duration_rounds: int | None = None,
) -> bool:
    """
    Temporarily suppress a condition's effects.

    Args:
        target: The ObjectDB instance
        condition: ConditionTemplate instance
        duration_rounds: Rounds to suppress (None = indefinite)

    Returns:
        True if condition was suppressed
    """
    instance = get_condition_instance(target, condition, include_suppressed=True)
    if not instance:
        return False

    instance.is_suppressed = True
    if duration_rounds:
        instance.suppressed_until = timezone.now() + timedelta(
            seconds=duration_rounds * SECONDS_PER_ROUND
        )
    instance.save()
    return True


def unsuppress_condition(
    target: "ObjectDB",
    condition: ConditionTemplate,
) -> bool:
    """
    Remove suppression from a condition.

    Args:
        target: The ObjectDB instance
        condition: ConditionTemplate instance

    Returns:
        True if condition was unsuppressed
    """
    instance = get_condition_instance(target, condition, include_suppressed=True)
    if not instance:
        return False

    instance.is_suppressed = False
    instance.suppressed_until = None
    instance.save()
    return True


def clear_all_conditions(
    target: "ObjectDB",
    *,
    only_negative: bool = False,
    only_category: "ConditionCategory | None" = None,
) -> int:
    """
    Remove all conditions from a target.

    Args:
        target: The ObjectDB instance
        only_negative: Only clear negative conditions
        only_category: Only clear conditions in this category instance

    Returns:
        Number of conditions removed
    """
    qs = ConditionInstance.objects.filter(target=target)

    if only_negative:
        qs = qs.filter(condition__category__is_negative=True)

    if only_category:
        qs = qs.filter(condition__category=only_category)

    count = qs.count()
    qs.delete()
    return count


def get_turn_order_modifier(target: "ObjectDB") -> int:
    """
    Get the total turn order modifier from all conditions.

    Args:
        target: The ObjectDB instance

    Returns:
        Integer modifier to turn order (positive = act earlier)
    """
    result = (
        get_active_conditions(target)
        .filter(condition__affects_turn_order=True)
        .aggregate(total=Coalesce(Sum("condition__turn_order_modifier"), 0))
    )
    return result["total"]


def get_aggro_priority(target: "ObjectDB") -> int:
    """
    Get the total aggro priority from all conditions.

    Args:
        target: The ObjectDB instance

    Returns:
        Integer priority (higher = more likely to be targeted)
    """
    result = (
        get_active_conditions(target)
        .filter(condition__draws_aggro=True)
        .aggregate(total=Coalesce(Sum("condition__aggro_priority"), 0))
    )
    return result["total"]


# =============================================================================
# Percentage Modifier Queries (from Distinctions)
# =============================================================================


def _get_condition_percent_modifier(
    target: "ObjectDB",
    category_name: str,
    condition_name: str,
) -> int:
    """
    Get total percentage modifier for a condition effect category.

    Queries CharacterModifier for modifiers targeting the specified
    condition percentage category and condition name.

    Args:
        target: The ObjectDB instance (character)
        category_name: Modifier category (e.g., "condition_control_percent")
        condition_name: Condition name to match (e.g., "anger")

    Returns:
        Total percentage modifier (e.g., 100 means +100%)
    """
    try:
        sheet = target.sheet_data
    except AttributeError:
        return 0

    modifiers = CharacterModifier.objects.filter(
        character=sheet,
        target__category__name=category_name,
        target__name__iexact=condition_name,
    )

    return sum(m.value for m in modifiers)


def get_condition_control_percent_modifier(
    target: "ObjectDB",
    condition_name: str,
) -> int:
    """
    Get percentage modifier to control loss rate for a condition.

    Used by emotional conditions like anger to determine how quickly
    a character loses control. A +100% modifier doubles the control loss rate.

    Args:
        target: The character ObjectDB instance
        condition_name: Condition name (e.g., "anger")

    Returns:
        Total percentage modifier (e.g., 100 for Wrathful)
    """
    return _get_condition_percent_modifier(target, "condition_control_percent", condition_name)


def get_condition_intensity_percent_modifier(
    target: "ObjectDB",
    condition_name: str,
) -> int:
    """
    Get percentage modifier to intensity gain for a condition.

    Used by emotional conditions like anger to determine how much
    intensity is gained when the condition intensifies. A +50% modifier
    means 1.5x normal intensity gain.

    Args:
        target: The character ObjectDB instance
        condition_name: Condition name (e.g., "anger")

    Returns:
        Total percentage modifier (e.g., 50 for Wrathful)
    """
    return _get_condition_percent_modifier(target, "condition_intensity_percent", condition_name)


def get_condition_penalty_percent_modifier(
    target: "ObjectDB",
    condition_name: str,
) -> int:
    """
    Get percentage modifier to check penalties for a condition.

    Used by conditions like humbled to determine how severe the check
    penalties are. A +100% modifier doubles all check penalties.

    Args:
        target: The character ObjectDB instance
        condition_name: Condition name (e.g., "humbled")

    Returns:
        Total percentage modifier (e.g., 100 for Hubris)
    """
    return _get_condition_percent_modifier(target, "condition_penalty_percent", condition_name)


# =============================================================================
# Severity-Driven Advancement
# =============================================================================


def advance_condition_severity(
    instance: ConditionInstance,
    amount: int,
) -> SeverityAdvanceResult:
    """Increment a condition's severity and advance stage if threshold crossed.

    Used for conditions like Soulfray where severity accumulates from
    external events rather than being set once at creation.

    Stages with severity_threshold=None are ignored (time-based only).
    Can skip multiple stages if the severity jump is large enough.
    """
    previous_stage = instance.current_stage
    instance.severity += amount

    # Find the highest severity-threshold stage that's been reached
    new_stage = (
        instance.condition.stages.filter(
            severity_threshold__isnull=False,
            severity_threshold__lte=instance.severity,
        )
        .order_by("-severity_threshold")
        .first()
    )

    stage_changed = False
    if new_stage and new_stage != previous_stage:
        instance.current_stage = new_stage
        stage_changed = True

    update_fields = ["severity", "current_stage"]
    if instance.severity > 0 and instance.resolved_at is not None:
        instance.resolved_at = None
        update_fields.append("resolved_at")

    instance.save(update_fields=update_fields)

    if stage_changed:
        target_location = getattr(instance.target, "location", None)  # noqa: GETATTR_LITERAL
        if target_location is not None:
            emit_event(
                EventName.CONDITION_STAGE_CHANGED,
                ConditionStageChangedPayload(
                    target=instance.target,
                    instance=instance,
                    old_stage=previous_stage,
                    new_stage=instance.current_stage,
                ),
                location=target_location,
            )

    # Inline dispatch of the stage-entry aftermath hook. The reactive layer
    # dispatches only to DB Trigger rows; Python subscribers use the inline
    # pattern (see apply_damage_reduction_from_threads in magic/services.py).
    # Only ascending transitions apply aftermath — apply_stage_entry_aftermath
    # gates internally on stage_order comparison.
    if stage_changed:
        apply_stage_entry_aftermath(
            ConditionStageChangedPayload(
                target=instance.target,
                instance=instance,
                old_stage=previous_stage,
                new_stage=instance.current_stage,
            ),
        )

    return SeverityAdvanceResult(
        previous_stage=previous_stage,
        new_stage=instance.current_stage,
        stage_changed=stage_changed,
        total_severity=instance.severity,
    )


def apply_stage_entry_aftermath(payload: ConditionStageChangedPayload) -> None:
    """On ascending stage changes, apply the stage's on_entry_conditions.

    Per spec §5.6. Callers pass a ConditionStageChangedPayload frozen
    dataclass (the same payload emitted by advance_condition_severity).
    Gates:
    - new_stage is None → no-op (fully decayed).
    - old_stage.stage_order >= new_stage.stage_order → descending or
      sideways; no-op.
    Idempotency: existing aftermath instance with severity >= assoc.severity
    is left alone; lower severity is advanced to assoc.severity.
    """
    old = payload.old_stage
    new = payload.new_stage
    if new is None:
        return
    if old is not None and new.stage_order <= old.stage_order:
        return
    target = payload.target

    for assoc in new.on_entry_assocs.select_related("condition").all():
        existing = ConditionInstance.objects.filter(
            target=target,
            condition=assoc.condition,
            resolved_at__isnull=True,
        ).first()
        if existing is None:
            apply_condition(
                target,
                assoc.condition,
                severity=assoc.severity,
                source_description=f"on_entry of {new.name}",
            )
        elif existing.severity < assoc.severity:
            advance_condition_severity(existing, assoc.severity - existing.severity)
        # else: existing severity >= assoc.severity — leave alone.


def decay_condition_severity(
    instance: ConditionInstance,
    amount: int,
) -> SeverityDecayResult:
    """Inverse of advance_condition_severity. Walks stage down if threshold crossed.

    Per spec Scope 6 §5.3. Emits CONDITION_STAGE_CHANGED only when the stage
    actually changes; consumers derive descending-vs-ascending from
    stage_order comparison. Sets resolved_at when severity reaches 0.
    """
    previous_stage = instance.current_stage
    new_severity = max(0, instance.severity - amount)

    new_stage = (
        instance.condition.stages.filter(
            severity_threshold__isnull=False,
            severity_threshold__lte=new_severity,
        )
        .order_by("-severity_threshold")
        .first()
    )

    instance.severity = new_severity
    instance.current_stage = new_stage
    update_fields = ["severity", "current_stage"]

    resolved = new_severity == 0
    if resolved:
        instance.resolved_at = get_ic_now() or timezone.now()
        update_fields.append("resolved_at")

    instance.save(update_fields=update_fields)

    if new_stage != previous_stage:
        target_location = getattr(instance.target, "location", None)  # noqa: GETATTR_LITERAL
        if target_location is not None:
            emit_event(
                EventName.CONDITION_STAGE_CHANGED,
                ConditionStageChangedPayload(
                    target=instance.target,
                    instance=instance,
                    old_stage=previous_stage,
                    new_stage=new_stage,
                ),
                location=target_location,
            )

    return SeverityDecayResult(
        previous_stage=previous_stage,
        new_stage=new_stage,
        new_severity=new_severity,
        resolved=resolved,
    )


def decay_all_conditions_tick() -> DecayTickSummary:
    """Scheduler entry point. Decays all opt-in conditions by one tick.

    Per spec Scope 6 §5.4. Skips:
    - instances whose template sets passive_decay_blocked_in_engagement=True
      and whose target is an engaged character
    - instances where severity exceeds passive_decay_max_severity
    """
    from world.mechanics.engagement import CharacterEngagement  # noqa: PLC0415

    examined = 0
    ticked = 0
    engagement_blocked = 0
    severity_gated = 0

    qs = ConditionInstance.objects.filter(
        resolved_at__isnull=True,
        condition__passive_decay_per_day__gt=0,
    ).select_related("condition", "current_stage", "target")

    for instance in qs:
        examined += 1
        cond = instance.condition
        if (
            cond.passive_decay_blocked_in_engagement
            and CharacterEngagement.objects.filter(
                character=instance.target,
            ).exists()
        ):
            engagement_blocked += 1
            continue
        if (
            cond.passive_decay_max_severity is not None
            and instance.severity > cond.passive_decay_max_severity
        ):
            severity_gated += 1
            continue
        decay_condition_severity(instance, cond.passive_decay_per_day)
        ticked += 1

    return DecayTickSummary(
        examined=examined,
        ticked=ticked,
        engagement_blocked=engagement_blocked,
        severity_gated=severity_gated,
    )
