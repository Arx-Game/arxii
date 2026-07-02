"""Read shapes for the justice app (#1765)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from world.justice.constants import HeatTier

if TYPE_CHECKING:
    from world.justice.models import HeatSource


@dataclass(frozen=True)
class HeatReading:
    """The pursuit picture for one persona at one spot: summed value + display tier."""

    value: int
    tier: HeatTier
    sources: list[HeatSource] = field(default_factory=list)

    @property
    def is_safe(self) -> bool:
        return self.tier == HeatTier.SAFE
