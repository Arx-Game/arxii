"""Typed result shapes for currency services (#930)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.items.models import MaterialCategory


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
    # Materials ride the same dispatch (Build 0b): net common value landed in the house's
    # OrgMaterialStock, plus the Rare-Find stones delivered to / lost by the collector.
    material_value_landed: int = 0
    # Per-category breakdown of ``material_value_landed`` (sums to it exactly); empty on
    # catastrophe.
    landed_by_category: list[tuple[MaterialCategory, int]] = field(default_factory=list)
    stones_delivered: int = 0
    stones_lost: int = 0

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
class MaterialAllowanceResult:
    """Outcome of one non-discretionary materials allowance distribution (#2540 slice 2).

    The materials analogue of ``AllowanceResult`` — "the crafting draw". ``total_by_category``
    is the per-category value actually credited to members (sums the ``per_member`` share
    times ``member_count``; only categories with a positive credited total appear, so it never
    carries a zero entry); ``member_count`` is how many active piloted members shared it.
    """

    total_by_category: list[tuple[MaterialCategory, int]]
    member_count: int


@dataclass(frozen=True)
class ImprovementResult:
    """Outcome of one domain-investment attempt."""

    success_level: int
    gross_raised: bool
    graft_cracked: bool
    new_graft_pct: int


@dataclass(frozen=True)
class DistributionResult:
    """Outcome of one full collection-distribution dispatch (#2540, ruled 2026-07-20).

    Sequence: collect -> debt principal (a flat share of gross, first) -> member
    allowance (from the post-debt remainder) -> materials allowance (a share of what
    the collection landed per category, #2540 slice 2). ``debt_principal_paid`` is the
    coppers that left the treasury toward principal this dispatch.
    """

    collection: CollectionResult
    debt_principal_paid: int
    allowance: AllowanceResult
    material_allowance: MaterialAllowanceResult
