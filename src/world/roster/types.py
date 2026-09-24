"""Type declarations for the roster system."""

from dataclasses import dataclass
from typing import TypedDict


@dataclass(frozen=True)
class SlotHolder:
    """One thing occupying (or parked in) an account's character slots (#3996).

    ``kind`` is ``character`` (a current tenure), ``frozen`` (a tenure whose character
    is frozen: kept, but not counted), ``draft`` (an open character-creation draft) or
    ``application`` (a pending roster application). ``activity`` is True when the
    holder is a roster character with an activity requirement, the one kind capped at
    a single slot.
    """

    kind: str
    name: str
    roster_entry_id: int | None
    counts: bool
    activity: bool


@dataclass(frozen=True)
class CharacterSlots:
    """An account's slot ledger (#3996). ``total`` is None for an exempt account."""

    total: int | None
    used: int
    activity_total: int
    activity_used: int
    holders: list[SlotHolder]

    @property
    def exempt(self) -> bool:
        return self.total is None

    @property
    def has_free_slot(self) -> bool:
        return self.total is None or self.used < self.total

    @property
    def has_free_activity_slot(self) -> bool:
        return self.total is None or self.activity_used < self.activity_total


class PolicyIssue(TypedDict):
    code: str
    message: str


class PolicyInfo(TypedDict):
    basic_eligibility: str
    policy_issues: list[PolicyIssue]
    requires_staff_review: bool
    auto_approvable: bool
    player_current_characters: list[str]
    character_previous_players: int
