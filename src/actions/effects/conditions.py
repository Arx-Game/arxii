"""Handlers for condition-related effect configs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from actions.effects.base import apply_immunity_on_fail, resolve_target_difficulty
from world.checks.services import perform_check
from world.conditions.services import apply_condition, has_condition, remove_condition
from world.magic.services.magic_skills import technique_skill_term

if TYPE_CHECKING:
    from actions.models import ConditionOnCheckConfig, RemoveConditionOnCheckConfig
    from actions.types import ActionContext
    from world.checks.types import ExtraTraitTerm


def _technique_skill_terms(
    context: ActionContext, config: ConditionOnCheckConfig | RemoveConditionOnCheckConfig
) -> tuple[ExtraTraitTerm, ...]:
    """The roll's technique skill term when the effect's enhancement source is a technique.

    The source is the config's ``ActionEnhancement`` (its ``technique`` FK is set exactly
    when ``source_type`` is TECHNIQUE, by a DB constraint). A distinction or condition source
    adds nothing, and so does a technique with no resolvable skill (#4477).
    """
    technique = config.enhancement.technique
    if technique is None or context.actor is None:
        return ()
    term = technique_skill_term(context.actor, technique)
    return (term,) if term is not None else ()


def handle_condition_on_check(context: ActionContext, config: ConditionOnCheckConfig) -> None:
    """Apply a condition to the target, gated by a check roll.

    Steps:
    1. Skip if no target
    2. Check immunity -- skip if target has immunity_condition
    3. Resolve target difficulty from resistance_check_type or fixed value
    4. Roll attacker's check_type vs resolved difficulty
    5. On success: apply condition
    6. On failure: apply immunity if configured
    """
    if context.target is None:
        return

    # Step 1: Check immunity
    if has_condition(context.target, config.immunity_condition):
        return

    # Step 2: Resolve difficulty
    target_difficulty = resolve_target_difficulty(
        context.target,
        config.resistance_check_type,
        config.target_difficulty,
    )

    # Step 3: Roll
    result = perform_check(
        context.actor,
        config.check_type,
        target_difficulty=target_difficulty,
        extra_traits=_technique_skill_terms(context, config),
    )

    # Step 4: Apply condition or immunity
    if result.success_level > 0:
        apply_condition(
            context.target,
            config.condition,
            severity=config.severity,
            duration_rounds=config.duration_rounds,
            source_character=context.actor,
            source_description=config.source_description,
        )
    elif config.immunity_condition is not None and config.immunity_duration is not None:
        apply_immunity_on_fail(
            context.target,
            config.immunity_condition,
            config.immunity_duration,
        )


def handle_remove_condition_on_check(
    context: ActionContext, config: RemoveConditionOnCheckConfig
) -> None:
    """Remove a condition from the target, gated by a check roll.

    Steps:
    1. Skip if no target
    2. Resolve target difficulty from resistance_check_type or fixed value
    3. Roll attacker's check_type vs resolved difficulty
    4. On success: remove condition (graceful no-op if target lacks it)
    """
    if context.target is None:
        return

    # Resolve difficulty
    target_difficulty = resolve_target_difficulty(
        context.target,
        config.resistance_check_type,
        config.target_difficulty,
    )

    # Roll
    result = perform_check(
        context.actor,
        config.check_type,
        target_difficulty=target_difficulty,
        extra_traits=_technique_skill_terms(context, config),
    )

    # Remove condition on success; remove_condition returns False if absent (graceful)
    if result.success_level > 0:
        remove_condition(context.target, config.condition)
