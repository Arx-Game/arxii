"""Typed result shapes for currency services (#930)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CollectionResult:
    """Outcome of one collection dispatch across an org's income streams.

    ``gathered`` is what the collector set out with (the summed pools, all
    zeroed by the attempt); ``landed`` is what reached the treasury after the
    outcome band and graft; ``success_level`` is the check band that decided
    it. ``catastrophe`` marks the nothing-lands band (the collector-incident
    seam — combat-domain follow-up).
    """

    gathered: int
    landed: int
    graft_leak: int
    success_level: int
    catastrophe: bool = False
    # Gems ride the same dispatch (Build 0b): net common value landed in the house's
    # OrgGemStock, plus the Rare-Find stones delivered to / lost by the collector.
    gem_value_landed: int = 0
    stones_delivered: int = 0
    stones_lost: int = 0

    @property
    def stolen(self) -> int:
        return max(0, self.gathered - self.landed - self.graft_leak)


@dataclass(frozen=True)
class ImprovementResult:
    """Outcome of one domain-investment attempt."""

    success_level: int
    gross_raised: bool
    graft_cracked: bool
    new_graft_pct: int
