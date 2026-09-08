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
    #: What opens this offer, as a stable grouping key (#3709): ``prompt:never_do``,
    #: ``reason:<id>``, ``degree:ruined``, ``section:<id>``; the leaf mounts one block
    #: per key. ``DistinctionOffer.opener_key``.
    opener_key: str = ""
    #: The draft's Beginning pinned this line into the few shown at rest (#3709).
    first_look: bool = False
    #: The distinction is already in the draft from a different offer (#3709): the
    #: leaf prints it held, never offers it twice.
    held: bool = False
    #: The compact mechanics line, "+Deception; -Willpower" (#3709), built from the
    #: distinction's effect rows by ``offers.effect_line``.
    effect_line: str = ""


@dataclass(frozen=True)
class ClosedDistinction:
    """One distinction a route's ``closed_distinctions`` hides from every chapter (#3675).

    Built by ``world.character_creation.offers.closed_for`` so a chapter can print
    the route's closed line instead of silently omitting the option.
    """

    distinction_id: int
    name: str
    reason: str
    #: Opener labels of the requesting chapter's own active offers for this
    #: distinction whose opener the draft satisfies (#3675 fix round 2); lets a
    #: chapter mount (the Glimpse's ``GlimpseAxes``) print the closed hint once,
    #: under the specific pick that would have opened it, instead of under every
    #: pick. Empty when no offer in this chapter opens it (every chapter's offers
    #: carry an opener since #3709: a prompt, a reason or degree, a section).
    opener_labels: list[str]
    #: The same offers' ids, index-aligned with ``opener_labels`` (#3675 final fix
    #: B4). A caller that needs to match a closed row to a specific offer (a
    #: Glimpse tag's own offer ids) uses this, never a name/label match.
    opener_ids: list[int]


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
