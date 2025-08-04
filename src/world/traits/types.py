"""
Type definitions for the traits system.

Contains dataclasses, TypedDicts, and other type declarations that need to be
shared across modules without creating circular import issues.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.traits.models import CheckOutcome, CheckRank, ResultChart


@dataclass
class CheckResult:
    """
    Structured result from a trait check resolution.

    Contains all information needed to understand and display check outcomes
    while maintaining proper typing and object references.
    """

    roller: "ObjectDB"
    roller_traits: List[str]
    roller_points: int
    roller_rank: Optional["CheckRank"]
    target_points: int
    target_rank: Optional["CheckRank"]
    rank_difference: int
    chart: Optional["ResultChart"]
    roll: int
    outcome: Optional["CheckOutcome"]

    @property
    def roller_name(self) -> str:
        """Get the roller's display name."""
        return self.roller.key

    @property
    def roller_rank_name(self) -> str:
        """Get the roller's rank name or 'Unranked'."""
        return self.roller_rank.name if self.roller_rank else "Unranked"

    @property
    def target_rank_name(self) -> str:
        """Get the target's rank name or 'Unranked'."""
        return self.target_rank.name if self.target_rank else "Unranked"

    @property
    def chart_name(self) -> str:
        """Get the chart name or indicate no chart found."""
        return self.chart.name if self.chart else "No Chart Found"

    @property
    def outcome_name(self) -> str:
        """Get the outcome name or 'Unknown'."""
        return self.outcome.name if self.outcome else "Unknown"

    @property
    def outcome_description(self) -> str:
        """Get the outcome description."""
        return self.outcome.description if self.outcome else ""

    @property
    def success_level(self) -> int:
        """Get the numeric success level."""
        return self.outcome.success_level if self.outcome else 0

    def __str__(self) -> str:
        """String representation for debugging and display."""
        return (
            f"CheckResult(roller={self.roller_name}, "
            f"traits={self.roller_traits}, "
            f"roll={self.roll}, "
            f"outcome={self.outcome_name})"
        )
