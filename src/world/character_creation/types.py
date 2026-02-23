"""Type declarations for character creation."""

from dataclasses import dataclass, field
from typing import TypedDict


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


@dataclass
class ResonanceSource:
    """A single distinction's contribution to a projected resonance."""

    distinction_name: str
    value: int


@dataclass
class ProjectedResonance:
    """Projected resonance total from a draft's selected distinctions."""

    resonance_id: int
    resonance_name: str
    total: int
    sources: list[ResonanceSource] = field(default_factory=list)
