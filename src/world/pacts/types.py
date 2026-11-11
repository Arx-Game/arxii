"""Result and read-model dataclasses for being pacts (#4341)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from world.pacts.models import CharacterPact


@dataclass(frozen=True)
class PactStageLine:
    """One stage of a pact's condition as the offer and the card list it."""

    name: str
    threshold: int
    effects: tuple[str, ...]


@dataclass(frozen=True)
class PactSourceLine:
    """Favor credited toward the current period from one kind of source."""

    label: str
    favor: int


@dataclass(frozen=True)
class PeriodGrade:
    """What grading one pact period did.

    ``severity_change`` is signed (positive rose, negative eased). ``resist_outcome``
    names the resist roll's tier as applied (a botch is already lifted to Failure),
    empty when no roll was needed. ``breached`` is True when the last stage applied.
    """

    earned: int
    required: int
    severity_change: int
    resist_outcome: str
    stage_before: str
    stage_after: str
    breached: bool


@dataclass(frozen=True)
class PactOfferSummary:
    """A pact offer as the pledge card shows it, built from the offer's rows."""

    being_name: str
    offer_name: str
    offer_text: str
    period_weeks: int
    favor_per_period: tuple[int, ...]
    promises: tuple[str, ...]
    condition_effects: tuple[str, ...]
    stages: tuple[PactStageLine, ...]


@dataclass(frozen=True)
class PactCard:
    """A character's pact as her card shows it.

    ``earned``/``required``/``time_limit`` describe the open period (a commitment
    period while the pact holds, an ease-out period after it ended; ``required`` is 0
    for an ease-out period). ``condition_effects`` apply at every stage;
    ``stages`` lists each stage's own effects.
    """

    pact: CharacterPact
    being_name: str
    being_is_secret: bool
    offer_name: str
    period_weeks: int
    earned: int
    required: int
    time_limit: datetime | None
    sources: tuple[PactSourceLine, ...]
    stage_name: str
    severity: int
    next_stage_threshold: int | None
    promises: tuple[str, ...]
    condition_effects: tuple[str, ...]
    stages: tuple[PactStageLine, ...]
    is_active: bool
    dissolution_reason: str
