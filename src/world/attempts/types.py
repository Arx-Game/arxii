"""Type definitions for the attempt system."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.attempts.models import AttemptConsequence, AttemptTemplate
    from world.checks.types import CheckResult


@dataclass
class ConsequenceDisplay:
    """A single consequence for roulette display. No rollmod or real weights exposed."""

    label: str
    tier_name: str
    weight: int
    is_selected: bool


@dataclass
class AttemptResult:
    """Result from resolving an attempt. Returned by resolve_attempt()."""

    attempt_template: "AttemptTemplate"
    check_result: "CheckResult"
    consequence: "AttemptConsequence"
    all_consequences: list[ConsequenceDisplay]
