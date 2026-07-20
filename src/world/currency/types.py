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

    @property
    def stolen(self) -> int:
        return max(0, self.gathered - self.landed - self.graft_leak)


@dataclass(frozen=True)
class AllowanceResult:
    """Outcome of one non-discretionary allowance distribution (#2540).

    ``total_distributed`` is the coppers that left the treasury; ``per_member`` is each active
    piloted member's equal share; ``member_count`` is how many received it.
    """

    total_distributed: int
    per_member: int
    member_count: int


@dataclass(frozen=True)
class ImprovementResult:
    """Outcome of one domain-investment attempt."""

    success_level: int
    gross_raised: bool
    graft_cracked: bool
    new_graft_pct: int
