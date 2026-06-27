"""Type definitions for the goals system."""

from dataclasses import dataclass
from typing import NotRequired, TypedDict


class GoalInputData(TypedDict):
    """
    Input shape for a single goal allocation.

    Used by CharacterGoalUpdateSerializer for validating goal updates.
    Frontend sends domain ID for proper PrimaryKeyRelatedField validation.
    Domain is a ModifierTarget with category='goal'.
    """

    domain: int  # ModifierTarget primary key (category='goal')
    points: int
    notes: NotRequired[str]


@dataclass
class GoalBonusBreakdown:
    """Breakdown of goal bonus calculation for a single domain."""

    base_points: int
    percent_modifier: int
    final_bonus: int


_GOAL_ERROR_MESSAGES: dict[str, str] = {
    "REVISION_TOO_SOON": "You cannot revise your goals again yet.",
    "OVER_POINT_CAP": "Total goal points exceed the maximum of 30.",
    "DUPLICATE_DOMAIN": "Each goal domain may only be allocated once.",
}


class GoalError(Exception):
    """User-safe validation error from goal operations.

    Always raised with one of the class-level message constants. Use
    ``exc.user_message`` in API responses instead of ``str(exc)`` to
    avoid CodeQL information-exposure warnings. Mirrors ``JournalError``.
    """

    REVISION_TOO_SOON = _GOAL_ERROR_MESSAGES["REVISION_TOO_SOON"]
    OVER_POINT_CAP = _GOAL_ERROR_MESSAGES["OVER_POINT_CAP"]
    DUPLICATE_DOMAIN = _GOAL_ERROR_MESSAGES["DUPLICATE_DOMAIN"]

    @property
    def user_message(self) -> str:
        msg = self.args[0] if self.args else ""
        if msg in _GOAL_ERROR_MESSAGES.values():
            return msg
        return "An unexpected goal error occurred."
