"""Reading a draft's weighted resonance picks (#5123).

The gift stage stores ``draft_data["gift_resonance_weights"]``, a list of
``{"resonance_id", "weight"}``. Every reader (validation, finalize, the personalization
options, the teaching fit) goes through here so a malformed entry is dropped the same way
everywhere and "the heaviest pick" means one thing: the highest weight, the earlier pick
winning a tie.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from world.character_creation.constants import GIFT_RESONANCE_WEIGHTS_KEY


@dataclass(frozen=True)
class ResonanceWeight:
    """One pick: a resonance id and the creation points spread onto it."""

    resonance_id: int
    weight: int


def _whole_number(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def parse_resonance_weights(raw: Any) -> list[ResonanceWeight]:
    """The well-formed picks in ``raw``, heaviest first (a tie keeps the order given).

    An entry that is not a mapping with a whole ``resonance_id`` and ``weight`` is dropped;
    a validator that must refuse malformed input compares the length with ``raw``'s.
    """
    if not isinstance(raw, list):
        return []
    picks = [
        ResonanceWeight(entry["resonance_id"], entry["weight"])
        for entry in raw
        if isinstance(entry, Mapping)
        and _whole_number(entry.get("resonance_id"))
        and _whole_number(entry.get("weight"))
    ]
    return sorted(picks, key=lambda pick: -pick.weight)


def draft_resonance_weights(draft_data: Mapping[str, Any]) -> list[ResonanceWeight]:
    """The draft's weighted resonance picks, heaviest first."""
    return parse_resonance_weights(draft_data.get(GIFT_RESONANCE_WEIGHTS_KEY))


def draft_lead_resonance_id(draft_data: Mapping[str, Any]) -> int | None:
    """The heaviest pick's resonance id, or None with no picks."""
    picks = draft_resonance_weights(draft_data)
    return picks[0].resonance_id if picks else None
