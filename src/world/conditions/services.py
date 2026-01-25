"""
Condition Service Layer

Provides the interface for applying, removing, and querying conditions on targets.
Handles all interaction processing, modifier calculations, and round-based updates.

Design principles:
- Everything is math (no binary immunity)
- Intensity - Resistance = Net Value
- Bidirectional modifiers (conditions can be good or bad depending on context)
"""

import contextlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from world.conditions.models import (
    CapabilityType,
    CheckType,
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
    ResistanceModifierResult,
    RoundTickResult,
)

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


# =============================================================================
# Core Service Functions
# =============================================================================


def get_active_conditions(
    target: "ObjectDB",
    *,
    category_slug: str | None = None,
    condition_slug: str | None = None,
    include_suppressed: bool = False,
) -> QuerySet[ConditionInstance]:
    """
    Get active condition instances on a target.

    Args:
        target: The ObjectDB instance to query
        category_slug: Filter to specific category
        condition_slug: Filter to specific condition
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

    if category_slug:
        qs = qs.filter(condition__category__slug=category_slug)

    if condition_slug:
        qs = qs.filter(condition__slug=condition_slug)

    return qs


def has_condition(
    target: "ObjectDB",
    condition: ConditionTemplate | str,
    *,
    include_suppressed: bool = False,
) -> bool:
    """
    Check if target has a specific condition.

    Args:
        target: The ObjectDB instance
        condition: ConditionTemplate or slug string
        include_suppressed: Count suppressed conditions

    Returns:
        True if condition is present
    """
    if isinstance(condition, str):
        slug = condition
    else:
        slug = condition.slug

    return get_active_conditions(
        target, condition_slug=slug, include_suppressed=include_suppressed
    ).exists()


def get_condition_instance(
    target: "ObjectDB",
    condition: ConditionTemplate | str,
    *,
    include_suppressed: bool = False,
) -> ConditionInstance | None:
    """
    Get a specific condition instance on a target.

    Args:
        target: The ObjectDB instance
        condition: ConditionTemplate or slug string
        include_suppressed: Include suppressed conditions in search

    Returns:
        ConditionInstance or None
    """
    if isinstance(condition, str):
        slug = condition
    else:
        slug = condition.slug

    return get_active_conditions(
        target, condition_slug=slug, include_suppressed=include_suppressed
    ).first()


@dataclass
class _ApplyConditionParams:
    """Parameters for applying a condition (reduces argument count)."""

    target: "ObjectDB"
    severity: int = 1
    duration_rounds: int | None = None
    source_character: "ObjectDB | None" = None
    source_power: object = None
    source_description: str = ""


def _handle_stacking(
    existing: ConditionInstance,
    template: ConditionTemplate,
    params: _ApplyConditionParams,
    interaction_results: dict,
) -> ApplyConditionResult:
    """Handle stacking for an existing condition instance."""
    existing.stacks += 1

    if template.stack_behavior in (
        ConditionTemplate.StackBehavior.INTENSITY,
        ConditionTemplate.StackBehavior.BOTH,
    ):
        existing.severity = max(existing.severity, params.severity)

    if template.stack_behavior in (
        ConditionTemplate.StackBehavior.DURATION,
        ConditionTemplate.StackBehavior.BOTH,
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
        removed_conditions=interaction_results.get("removed", []),
        applied_conditions=interaction_results.get("applied", []),
    )


def _handle_refresh(
    existing: ConditionInstance,
    template: ConditionTemplate,
    params: _ApplyConditionParams,
    interaction_results: dict,
) -> ApplyConditionResult:
    """Handle refresh for a non-stackable existing condition."""
    if params.severity >= existing.severity:
        existing.severity = params.severity
        rounds = params.duration_rounds or template.default_duration_value
        if template.default_duration_type == ConditionTemplate.DurationType.ROUNDS:
            existing.rounds_remaining = rounds
        existing.save()

    return ApplyConditionResult(
        success=True,
        instance=existing,
        message=f"{template.name} refreshed",
        removed_conditions=interaction_results.get("removed", []),
        applied_conditions=interaction_results.get("applied", []),
    )


def _create_new_instance(
    template: ConditionTemplate,
    params: _ApplyConditionParams,
    interaction_results: dict,
) -> ApplyConditionResult:
    """Create a new condition instance."""
    rounds = params.duration_rounds or template.default_duration_value
    rounds_remaining = (
        rounds if template.default_duration_type == ConditionTemplate.DurationType.ROUNDS else None
    )

    # Get first stage for progressive conditions
    first_stage = None
    stage_rounds = None
    if template.has_progression:
        first_stage = template.stages.order_by("stage_order").first()
        if first_stage and first_stage.rounds_to_next:
            stage_rounds = first_stage.rounds_to_next

    instance = ConditionInstance.objects.create(
        target=params.target,
        condition=template,
        severity=params.severity,
        stacks=1,
        rounds_remaining=rounds_remaining,
        current_stage=first_stage,
        stage_rounds_remaining=stage_rounds,
        source_character=params.source_character,
        source_power=params.source_power,
        source_description=params.source_description,
    )

    return ApplyConditionResult(
        success=True,
        instance=instance,
        stacks_added=1,
        message=f"{template.name} applied",
        removed_conditions=interaction_results.get("removed", []),
        applied_conditions=interaction_results.get("applied", []),
    )


@transaction.atomic
def apply_condition(  # noqa: PLR0913
    target: "ObjectDB",
    condition: ConditionTemplate | str,
    *,
    severity: int = 1,
    duration_rounds: int | None = None,
    source_character: "ObjectDB | None" = None,
    source_power=None,
    source_description: str = "",
) -> ApplyConditionResult:
    """
    Apply a condition to a target, handling stacking and interactions.

    Args:
        target: The ObjectDB instance to apply to
        condition: ConditionTemplate or slug string
        severity: Intensity/potency of the condition
        duration_rounds: Override default duration (None uses template default)
        source_character: Who caused this condition
        source_power: What power caused this (FK to magic.Power)
        source_description: Freeform description

    Returns:
        ApplyConditionResult with outcome details
    """
    # Resolve condition template
    if isinstance(condition, str):
        try:
            template = ConditionTemplate.objects.get(slug=condition)
        except ConditionTemplate.DoesNotExist:
            return ApplyConditionResult(
                success=False,
                message=f"Unknown condition: {condition}",
            )
    else:
        template = condition

    # Check for prevention interactions from existing conditions
    prevention = _check_prevention_interactions(target, template)
    if prevention:
        return ApplyConditionResult(
            success=False,
            was_prevented=True,
            prevented_by=prevention,
            message=f"{template.name} was prevented by {prevention.name}",
        )

    # Process interactions that trigger on application
    interaction_results = _process_application_interactions(target, template)

    # Bundle parameters for helper functions
    params = _ApplyConditionParams(
        target=target,
        severity=severity,
        duration_rounds=duration_rounds,
        source_character=source_character,
        source_power=source_power,
        source_description=source_description,
    )

    # Check if condition already exists
    existing = get_condition_instance(target, template)

    if existing:
        if template.is_stackable:
            if existing.stacks < template.max_stacks:
                return _handle_stacking(existing, template, params, interaction_results)
            # Max stacks reached - just refresh duration/severity
            return _handle_refresh(existing, template, params, interaction_results)
        # Non-stackable - refresh
        return _handle_refresh(existing, template, params, interaction_results)

    return _create_new_instance(template, params, interaction_results)


@transaction.atomic
def remove_condition(
    target: "ObjectDB",
    condition: ConditionTemplate | str,
    *,
    remove_all_stacks: bool = True,
) -> bool:
    """
    Remove a condition from a target.

    Args:
        target: The ObjectDB instance
        condition: ConditionTemplate or slug string
        remove_all_stacks: If False, only remove one stack

    Returns:
        True if condition was removed
    """
    instance = get_condition_instance(target, condition)
    if not instance:
        return False

    if not remove_all_stacks and instance.stacks > 1:
        instance.stacks -= 1
        instance.save()
        return True

    instance.delete()
    return True


@transaction.atomic
def remove_conditions_by_category(
    target: "ObjectDB",
    category_slug: str,
) -> list[ConditionTemplate]:
    """
    Remove all conditions in a category from a target.

    Args:
        target: The ObjectDB instance
        category_slug: Category slug to remove

    Returns:
        List of removed ConditionTemplates
    """
    instances = get_active_conditions(target, category_slug=category_slug)
    removed = [i.condition for i in instances]
    instances.delete()
    return removed


# =============================================================================
# Interaction Processing
# =============================================================================


def _check_prevention_interactions(
    target: "ObjectDB",
    incoming_condition: ConditionTemplate,
) -> ConditionTemplate | None:
    """
    Check if any existing condition prevents the incoming condition.

    Returns the preventing condition template, or None.
    """
    existing_conditions = get_active_conditions(target).values_list("condition_id", flat=True)

    # Check if any existing condition prevents this one
    prevention = (
        ConditionConditionInteraction.objects.filter(
            condition_id__in=existing_conditions,
            other_condition=incoming_condition,
            trigger=ConditionConditionInteraction.TriggerType.ON_OTHER_APPLIED,
            outcome=ConditionConditionInteraction.OutcomeType.PREVENT_OTHER,
        )
        .select_related("condition")
        .order_by("-priority")
        .first()
    )

    if prevention:
        return prevention.condition

    # Check if incoming condition would be prevented by its own interactions
    self_prevention = (
        ConditionConditionInteraction.objects.filter(
            condition=incoming_condition,
            other_condition_id__in=existing_conditions,
            trigger=ConditionConditionInteraction.TriggerType.ON_SELF_APPLIED,
            outcome=ConditionConditionInteraction.OutcomeType.PREVENT_SELF,
        )
        .select_related("other_condition")
        .order_by("-priority")
        .first()
    )

    if self_prevention:
        return self_prevention.other_condition

    return None


def _should_remove_existing(
    interaction: ConditionConditionInteraction,
    incoming_condition: ConditionTemplate,
) -> bool:
    """Determine if an interaction should remove the existing condition."""
    outcome = interaction.outcome
    is_existing_owner = interaction.condition != incoming_condition

    if outcome == ConditionConditionInteraction.OutcomeType.REMOVE_SELF:
        # Remove self = existing condition removes itself when it reacts
        return is_existing_owner

    if outcome == ConditionConditionInteraction.OutcomeType.REMOVE_OTHER:
        # Remove other = incoming's interaction removes the existing
        return not is_existing_owner

    if outcome in (
        ConditionConditionInteraction.OutcomeType.REMOVE_BOTH,
        ConditionConditionInteraction.OutcomeType.MERGE,
    ):
        # These always remove the existing condition
        return True

    return False


def _process_application_interactions(
    target: "ObjectDB",
    incoming_condition: ConditionTemplate,
) -> dict:
    """
    Process condition-condition interactions when a new condition is applied.

    Returns dict with 'removed' and 'applied' condition lists.
    """
    result: dict = {"removed": [], "applied": []}

    existing_instances = list(get_active_conditions(target))
    existing_condition_ids = [i.condition_id for i in existing_instances]

    # Find all relevant interactions, ordered by priority
    interactions = ConditionConditionInteraction.objects.filter(
        Q(
            condition=incoming_condition,
            other_condition_id__in=existing_condition_ids,
            trigger=ConditionConditionInteraction.TriggerType.ON_SELF_APPLIED,
        )
        | Q(
            condition_id__in=existing_condition_ids,
            other_condition=incoming_condition,
            trigger=ConditionConditionInteraction.TriggerType.ON_OTHER_APPLIED,
        )
    ).order_by("-priority")

    for interaction in interactions:
        # Find the existing instance this interaction affects
        if interaction.condition == incoming_condition:
            match_id = interaction.other_condition_id
        else:
            match_id = interaction.condition_id

        existing_instance = next(
            (i for i in existing_instances if i.condition_id == match_id),
            None,
        )

        if not existing_instance:
            continue

        if _should_remove_existing(interaction, incoming_condition):
            result["removed"].append(existing_instance.condition)
            existing_instance.delete()
            existing_instances.remove(existing_instance)

    return result


@transaction.atomic
def process_damage_interactions(
    target: "ObjectDB",
    damage_type: DamageType | str,
) -> DamageInteractionResult:
    """
    Process condition interactions when target takes damage.

    Args:
        target: The ObjectDB taking damage
        damage_type: DamageType or slug string

    Returns:
        DamageInteractionResult with modifier percent and condition changes.
        Caller applies the modifier to their damage calculation.
    """
    if isinstance(damage_type, str):
        try:
            dtype = DamageType.objects.get(slug=damage_type)
        except DamageType.DoesNotExist:
            return DamageInteractionResult()
    else:
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
    capability: CapabilityType | str,
) -> CapabilityStatus:
    """
    Get the status of a capability for a target based on active conditions.

    Args:
        target: The ObjectDB instance
        capability: CapabilityType or slug string

    Returns:
        CapabilityStatus with block status and modifiers
    """
    if isinstance(capability, str):
        try:
            cap = CapabilityType.objects.get(slug=capability)
        except CapabilityType.DoesNotExist:
            return CapabilityStatus()
    else:
        cap = capability

    result = CapabilityStatus(
        is_blocked=False,
        modifier_percent=0,
        blocking_conditions=[],
    )

    active_instances = get_active_conditions(target)

    for instance in active_instances:
        # Get effects that apply to this stage (or null = all stages)
        effects = ConditionCapabilityEffect.objects.filter(
            condition=instance.condition,
            capability=cap,
        ).filter(Q(stage__isnull=True) | Q(stage=instance.current_stage))

        for effect in effects:
            if effect.effect_type == ConditionCapabilityEffect.EffectType.BLOCKED:
                result.is_blocked = True
                result.blocking_conditions.append(instance)

            elif effect.effect_type in (
                ConditionCapabilityEffect.EffectType.REDUCED,
                ConditionCapabilityEffect.EffectType.ENHANCED,
            ):
                # Scale by severity multiplier if applicable
                modifier = effect.modifier_percent
                if instance.current_stage:
                    modifier = int(modifier * instance.current_stage.severity_multiplier)
                result.modifier_percent += modifier

    return result


def get_check_modifier(
    target: "ObjectDB",
    check_type: CheckType | str,
) -> CheckModifierResult:
    """
    Get the total modifier for a check type from active conditions.

    Args:
        target: The ObjectDB instance
        check_type: CheckType or slug string

    Returns:
        CheckModifierResult with total and breakdown
    """
    if isinstance(check_type, str):
        try:
            ctype = CheckType.objects.get(slug=check_type)
        except CheckType.DoesNotExist:
            return CheckModifierResult()
    else:
        ctype = check_type

    result = CheckModifierResult(total_modifier=0, breakdown=[])

    active_instances = get_active_conditions(target)

    for instance in active_instances:
        # Get modifiers that apply to this stage (or null = all stages)
        modifiers = ConditionCheckModifier.objects.filter(
            condition=instance.condition,
            check_type=ctype,
        ).filter(Q(stage__isnull=True) | Q(stage=instance.current_stage))

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
    damage_type: DamageType | str | None = None,
) -> ResistanceModifierResult:
    """
    Get the total resistance modifier for a damage type from active conditions.

    Args:
        target: The ObjectDB instance
        damage_type: DamageType or slug string, or None for "all damage" modifiers only

    Returns:
        ResistanceModifierResult with total and breakdown
    """
    dtype = None
    if isinstance(damage_type, str):
        with contextlib.suppress(DamageType.DoesNotExist):
            dtype = DamageType.objects.get(slug=damage_type)
    elif damage_type is not None:
        dtype = damage_type

    result = ResistanceModifierResult(total_modifier=0, breakdown=[])

    active_instances = get_active_conditions(target)

    for instance in active_instances:
        # Get modifiers for specific damage type AND "all damage" (null)
        modifiers = ConditionResistanceModifier.objects.filter(
            condition=instance.condition,
        ).filter(Q(stage__isnull=True) | Q(stage=instance.current_stage))

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
    return _process_round_tick(target, ConditionDamageOverTime.TickTiming.START_OF_ROUND)


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
    result = _process_round_tick(target, ConditionDamageOverTime.TickTiming.END_OF_ROUND)

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
    return _process_round_tick(target, ConditionDamageOverTime.TickTiming.ON_ACTION)


def _process_round_tick(
    target: "ObjectDB",
    timing: str,
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
        # Get DoT effects for this timing and stage
        dot_effects = ConditionDamageOverTime.objects.filter(
            condition=instance.condition,
            tick_timing=timing,
        ).filter(Q(stage__isnull=True) | Q(stage=instance.current_stage))

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
    condition: ConditionTemplate | str,
    *,
    duration_rounds: int | None = None,
) -> bool:
    """
    Temporarily suppress a condition's effects.

    Args:
        target: The ObjectDB instance
        condition: ConditionTemplate or slug string
        duration_rounds: Rounds to suppress (None = indefinite)

    Returns:
        True if condition was suppressed
    """
    instance = get_condition_instance(target, condition, include_suppressed=True)
    if not instance:
        return False

    instance.is_suppressed = True
    if duration_rounds:
        instance.suppressed_until = timezone.now() + timezone.timedelta(
            minutes=duration_rounds * 6  # Assuming 6 seconds per round
        )
    instance.save()
    return True


def unsuppress_condition(
    target: "ObjectDB",
    condition: ConditionTemplate | str,
) -> bool:
    """
    Remove suppression from a condition.

    Args:
        target: The ObjectDB instance
        condition: ConditionTemplate or slug string

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
    only_category: str | None = None,
) -> int:
    """
    Remove all conditions from a target.

    Args:
        target: The ObjectDB instance
        only_negative: Only clear negative conditions
        only_category: Only clear conditions in this category

    Returns:
        Number of conditions removed
    """
    qs = ConditionInstance.objects.filter(target=target)

    if only_negative:
        qs = qs.filter(condition__category__is_negative=True)

    if only_category:
        qs = qs.filter(condition__category__slug=only_category)

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
    total = 0
    for instance in get_active_conditions(target):
        if instance.condition.affects_turn_order:
            total += instance.condition.turn_order_modifier
    return total


def get_aggro_priority(target: "ObjectDB") -> int:
    """
    Get the total aggro priority from all conditions.

    Args:
        target: The ObjectDB instance

    Returns:
        Integer priority (higher = more likely to be targeted)
    """
    total = 0
    for instance in get_active_conditions(target):
        if instance.condition.draws_aggro:
            total += instance.condition.aggro_priority
    return total
