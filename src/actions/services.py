"""Service functions for action resolution."""

from __future__ import annotations

from typing import TYPE_CHECKING

from actions.types import WeightedConsequence

if TYPE_CHECKING:
    from actions.models import ConsequencePool
    from actions.models.consequence_pools import ConsequencePoolEntry


def get_effective_consequences(pool: ConsequencePool) -> list[WeightedConsequence]:
    """Resolve pool inheritance into a flat list of weighted consequences.

    For pools without a parent, returns the pool's own entries.
    For child pools, starts with the parent's entries, then applies
    the child's modifications (additions, exclusions, weight overrides).
    """
    entries = list(pool.entries.select_related("consequence"))

    if pool.parent_id is None:
        return _entries_to_weighted(entries)

    # Start with parent's effective consequences
    parent_entries = list(pool.parent.entries.select_related("consequence"))
    parent_by_consequence_id: dict[int, WeightedConsequence] = {}
    for entry in parent_entries:
        if entry.is_excluded:
            continue
        wc = _entry_to_weighted(entry)
        parent_by_consequence_id[entry.consequence_id] = wc

    # Apply child modifications
    for entry in entries:
        cid = entry.consequence_id
        if entry.is_excluded:
            parent_by_consequence_id.pop(cid, None)
        elif cid in parent_by_consequence_id:
            # Override weight
            if entry.weight_override is not None:
                parent_by_consequence_id[cid] = _entry_to_weighted(entry)
        else:
            # Add new consequence
            parent_by_consequence_id[cid] = _entry_to_weighted(entry)

    return list(parent_by_consequence_id.values())


def _entries_to_weighted(
    entries: list[ConsequencePoolEntry],
) -> list[WeightedConsequence]:
    """Convert pool entries to WeightedConsequence list, skipping excluded."""
    return [_entry_to_weighted(e) for e in entries if not e.is_excluded]


def _entry_to_weighted(entry: ConsequencePoolEntry) -> WeightedConsequence:
    """Convert a single ConsequencePoolEntry to WeightedConsequence."""
    consequence = entry.consequence
    weight_override = entry.weight_override
    return WeightedConsequence(
        consequence=consequence,
        weight=weight_override if weight_override is not None else consequence.weight,
        character_loss=consequence.character_loss,
    )
