"""Type definitions for the check system."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from world.checks.models import CheckType
    from world.traits.models import CheckOutcome, CheckRank, ResultChart


@dataclass
class CheckResult:
    """Result from a check resolution. No roll numbers exposed."""

    check_type: "CheckType"
    outcome: Optional["CheckOutcome"]
    chart: Optional["ResultChart"]
    roller_rank: Optional["CheckRank"]
    target_rank: Optional["CheckRank"]
    rank_difference: int
    trait_points: int
    aspect_bonus: int
    total_points: int

    @property
    def outcome_name(self) -> str:
        return str(self.outcome.name) if self.outcome else "Unknown"

    @property
    def success_level(self) -> int:
        return int(self.outcome.success_level) if self.outcome else 0

    @property
    def chart_name(self) -> str:
        return str(self.chart.name) if self.chart else "No Chart Found"
