"""Type definitions for the check system."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext
    from world.checks.models import CheckType, Consequence
    from world.mechanics.models import ChallengeInstance
    from world.traits.models import CheckOutcome, CheckRank, ResultChart


@dataclass
class OutcomeDisplay:
    """Single outcome for frontend roulette display. Used by any check-based system."""

    label: str
    tier_name: str
    weight: int
    is_selected: bool


@dataclass
class CheckResult:
    """Result from a check resolution. No roll numbers exposed."""

    check_type: CheckType
    outcome: CheckOutcome | None
    chart: ResultChart | None
    roller_rank: CheckRank | None
    target_rank: CheckRank | None
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


@dataclass
class ResolutionContext:
    """Carries character and typed optional source refs for consequence resolution."""

    character: ObjectDB
    challenge_instance: ChallengeInstance | None = None
    action_context: ActionContext | None = None

    @property
    def location(self) -> ObjectDB:
        return self.character.location  # type: ignore[return-value]

    @property
    def display_label(self) -> str:
        if self.challenge_instance is not None:
            return str(self.challenge_instance)
        if self.action_context is not None:
            return str(self.action_context)
        msg = "ResolutionContext has no populated source (challenge_instance or action_context)"
        raise ValueError(msg)


@dataclass
class PendingResolution:
    """Intermediate result for the two-step consequence pipeline."""

    check_result: CheckResult
    selected_consequence: Consequence
