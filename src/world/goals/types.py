"""Type definitions for the goals system."""

from typing import NotRequired, TypedDict


class GoalInputData(TypedDict):
    """
    Input shape for a single goal allocation.

    Used by CharacterGoalUpdateSerializer for validating goal updates.
    Frontend sends domain ID for proper PrimaryKeyRelatedField validation.
    Domain is a ModifierType with category='goal'.
    """

    domain: int  # ModifierType primary key (category='goal')
    points: int
    notes: NotRequired[str]
