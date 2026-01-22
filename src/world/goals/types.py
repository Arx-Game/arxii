"""Type definitions for the goals system."""

from typing import NotRequired, TypedDict


class GoalInputData(TypedDict):
    """
    Input shape for a single goal allocation.

    Used by CharacterGoalUpdateSerializer for validating goal updates.
    Frontend sends domain ID (not slug) for proper PrimaryKeyRelatedField validation.
    """

    domain: int  # GoalDomain primary key
    points: int
    notes: NotRequired[str]
