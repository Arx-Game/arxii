"""Shared reusable steps for effect handlers.

These are discrete functions that handlers compose. Each wraps an existing
service function with the parameter resolution needed by the effects system.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.checks.models import CheckType
    from world.conditions.models import ConditionTemplate


def check_immunity(
    target: ObjectDB,
    immunity_condition: ConditionTemplate | None,
) -> bool:
    """Return True if the target is immune (has the immunity condition)."""
    if immunity_condition is None:
        return False
    from world.conditions.services import has_condition  # noqa: PLC0415

    return has_condition(target, immunity_condition)


def resolve_target_difficulty(
    target: ObjectDB,
    resistance_check_type: CheckType | None,
    fallback_difficulty: int | None,
) -> int:
    """Compute the target's resistance as a point total for target_difficulty.

    Uses perform_check with difficulty=0 to get the target's raw points if
    resistance_check_type is set. Falls back to a fixed value for synthetic
    NPCs or mission contexts.
    """
    if resistance_check_type is not None:
        try:
            from world.checks.services import perform_check  # noqa: PLC0415

            result = perform_check(target, resistance_check_type, target_difficulty=0)
            if result.total_points > 0:
                return result.total_points
        except (AttributeError, TypeError):
            pass  # Target has no traits -- fall through to fallback

    return fallback_difficulty or 0


def apply_immunity_on_fail(
    target: ObjectDB,
    immunity_condition: ConditionTemplate,
    immunity_duration: int | None,
) -> None:
    """Apply a short-term immunity condition after a failed check."""
    from world.conditions.services import apply_condition  # noqa: PLC0415

    apply_condition(
        target,
        immunity_condition,
        severity=1,
        duration_rounds=immunity_duration,
        source_description="Immunity from failed effect",
    )
