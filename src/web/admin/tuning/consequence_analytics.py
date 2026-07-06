"""Consequence-pool inspector analytics for the Game Tuning dashboard (#1221 Task 3).

Annotates a `ConsequencePool`'s resolved entries (inherited from parent /
overridden by the child / excluded by the child) without reimplementing the
merge semantics already owned by `ConsequencePool.cached_consequences`
(`actions/models/consequence_pools.py:52`) — this module only adds display
annotations by separately reading the pool's own entries and its parent's
entries, then cross-referencing them against the already-resolved
`cached_consequences` list.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from actions.models.consequence_pools import ConsequencePool

if TYPE_CHECKING:
    from world.checks.models import Consequence


@dataclass(frozen=True)
class PoolEntryRow:
    """One resolved consequence row within a pool inspection."""

    consequence_label: str
    outcome_tier_name: str
    tier_success_level: int
    effective_weight: int
    selection_probability_within_tier: float
    inherited: bool  # came from parent pool, untouched by the child
    overridden: bool  # child re-declares the same consequence as its parent
    character_loss: bool
    theater: bool


@dataclass(frozen=True)
class PoolInspection:
    """Full annotated view of a single `ConsequencePool`."""

    pool_name: str
    parent_name: str | None
    rows: list[PoolEntryRow]  # grouped/ordered by success_level desc, then label
    excluded_labels: list[str]  # parent entries the child excluded


def list_pools() -> list[tuple[int, str]]:
    """(pk, name) pairs for every `ConsequencePool`, ordered by name, for the selector."""
    return list(ConsequencePool.objects.order_by("name").values_list("pk", "name"))


def inspect_pool(pool: ConsequencePool) -> PoolInspection:
    """Build a read-only annotated view of *pool*'s resolved consequence entries.

    Reuses `pool.cached_consequences` for the actual merge/exclusion/weight-override
    semantics — this function only derives inherited/overridden/excluded annotations
    by also reading the pool's own entries and, when present, the parent's entries.
    """
    own_entries = list(pool.entries.select_related("consequence", "consequence__outcome_tier"))
    own_by_cid = {e.consequence_id: e for e in own_entries}
    excluded_labels = [e.consequence.label for e in own_entries if e.is_excluded]

    consequence_by_id: dict[int, Consequence] = {
        e.consequence_id: e.consequence for e in own_entries
    }
    parent_cids: set[int] = set()
    if pool.parent_id is not None:
        parent_entries = list(
            pool.parent.entries.select_related("consequence", "consequence__outcome_tier")
        )
        parent_cids = {e.consequence_id for e in parent_entries if not e.is_excluded}
        for e in parent_entries:
            consequence_by_id.setdefault(e.consequence_id, e.consequence)

    weighted = pool.cached_consequences

    tier_totals: dict[int, int] = {}
    for wc in weighted:
        consequence = consequence_by_id[wc.consequence.pk]
        tier_totals[consequence.outcome_tier_id] = (
            tier_totals.get(consequence.outcome_tier_id, 0) + wc.weight
        )

    rows: list[PoolEntryRow] = []
    for wc in weighted:
        cid = wc.consequence.pk
        consequence = consequence_by_id[cid]
        has_own = cid in own_by_cid
        has_parent = cid in parent_cids
        tier_total = tier_totals[consequence.outcome_tier_id]
        probability = wc.weight / tier_total if tier_total else 0.0
        rows.append(
            PoolEntryRow(
                consequence_label=consequence.label,
                outcome_tier_name=consequence.outcome_tier.name,
                tier_success_level=consequence.outcome_tier.success_level,
                effective_weight=wc.weight,
                selection_probability_within_tier=probability,
                inherited=has_parent and not has_own,
                overridden=has_parent and has_own,
                character_loss=consequence.character_loss,
                theater=consequence.theater,
            )
        )

    rows.sort(key=lambda r: (-r.tier_success_level, r.consequence_label))

    return PoolInspection(
        pool_name=pool.name,
        parent_name=pool.parent.name if pool.parent_id is not None else None,
        rows=rows,
        excluded_labels=excluded_labels,
    )
