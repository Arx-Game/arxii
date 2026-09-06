"""Type declarations for character creation."""

from dataclasses import dataclass
from typing import TypedDict

# Stage number → list of human-readable error messages.
# Empty list means the stage is complete.
type StageValidationErrors = dict[int, list[str]]


@dataclass(frozen=True)
class VisibleOffer:
    """One priced choice a draft can see in a CG chapter (#3675).

    Built by ``world.character_creation.offers.offers_for`` for each chapter's
    serializer/view to render; carries its own mutual-exclusion lock state so
    the frontend never has to re-derive it.
    """

    offer_id: int
    distinction_id: int
    name: str
    player_line: str
    chapter: str
    arrives_as: str
    opener_label: str
    cost_per_rank: int
    max_rank: int
    is_locked: bool
    lock_reason: str


@dataclass(frozen=True)
class ClosedDistinction:
    """One distinction a route's ``closed_distinctions`` hides from every chapter (#3675).

    Built by ``world.character_creation.offers.closed_for`` so a chapter can print
    the route's closed line instead of silently omitting the option.
    """

    distinction_id: int
    name: str
    reason: str


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
