"""The result of one bonus resonance check (#5308)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.checks.models import CheckOutcome


@dataclass(frozen=True)
class GainBonus:
    """One bonus check result: the outcome rolled and the percent it adds to a gain.

    ``outcome`` is None when no check was rolled (the bonus check is off, or the roll had
    no chart), and ``percent`` is then 0.
    """

    outcome: CheckOutcome | None
    percent: int


NO_GAIN_BONUS = GainBonus(outcome=None, percent=0)
