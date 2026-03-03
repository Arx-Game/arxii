"""Type declarations for character creation."""

from typing import TypedDict

# Stage number → list of human-readable error messages.
# Empty list means the stage is complete.
type StageValidationErrors = dict[int, list[str]]


class StatAdjustment(TypedDict):
    """Result of a stat cap enforcement adjustment."""

    stat: str
    old_display: int
    new_display: int
    reason: str


class CGPointBreakdownEntry(TypedDict):
    """A single line item in the CG points breakdown."""

    category: str
    item: str
    cost: int
