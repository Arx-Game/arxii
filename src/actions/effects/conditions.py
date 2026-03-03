"""Handler for ConditionOnCheckConfig effects."""

from __future__ import annotations

from typing import TYPE_CHECKING

from actions.effects.base import apply_immunity_on_fail, resolve_target_difficulty
from world.checks.services import perform_check
from world.conditions.services import apply_condition, has_condition

if TYPE_CHECKING:
    from actions.effect_configs import ConditionOnCheckConfig
    from actions.types import ActionContext


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
    result = perform_check(context.actor, config.check_type, target_difficulty=target_difficulty)

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
