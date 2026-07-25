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

    Uses compute_check_rating to get the target's raw points if
    resistance_check_type is set. Falls back to a fixed value for synthetic
    NPCs or mission contexts.

    #2707: this used to call perform_check with target_difficulty=0 and read
    total_points, which rolls a die whose outcome is discarded and — worse —
    burns the target's rollmod (a secret staff story lever) as an invisible
    side effect. compute_check_rating computes the same pre-roll point total
    with no roll at all.
    """
    if resistance_check_type is not None:
        try:
            from world.checks.services import compute_check_rating  # noqa: PLC0415

            total_points = compute_check_rating(target, resistance_check_type)
            if total_points > 0:
                return total_points
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
