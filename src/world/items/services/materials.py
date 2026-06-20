"""Shared material-consumption helpers for crafting and ritual paths.

The ritual path (PerformRitualAction) and the crafting cost path (Task 4)
both need to tally/validate/consume ItemInstance stacks against a list of
requirements. This module extracts that logic into three pure-ish functions
that work over caller-supplied iterables — so neither path has to know about
the other's data source.

Caller contract
---------------
* ``available``: any iterable of ItemInstance-like objects. Each item must
  expose ``.pk``, ``.template_id``, ``.quality_tier_id``,
  ``.quality_tier`` (with ``.sort_order``), and ``.quantity``.
* ``requirements``: any iterable of requirement-like objects. Each must
  expose ``.item_template_id``, ``.min_quality_tier_id``,
  ``.min_quality_tier`` (with ``.sort_order`` when not None),
  and ``.quantity``.

Duck-typing means both RitualComponentRequirement + components_provided
and the future CraftingMaterialRequirement + holder-inventory slices work
without change.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from world.items.exceptions import InsufficientMaterials
from world.items.models import ItemInstance

if TYPE_CHECKING:
    pass  # no TYPE_CHECKING-only imports needed right now


def meets_quality_tier(inst: ItemInstance, requirement: object) -> bool:
    """Return True if ``inst`` satisfies ``requirement.min_quality_tier``.

    Args:
        inst: The ItemInstance being evaluated.
        requirement: A duck-typed requirement with ``min_quality_tier_id`` and
            ``min_quality_tier`` (with ``sort_order``) attributes.

    Returns:
        True when:
        - ``requirement.min_quality_tier_id`` is None (no minimum), OR
        - ``inst.quality_tier_id`` is not None and
          ``inst.quality_tier.sort_order >= requirement.min_quality_tier.sort_order``.
    """
    if requirement.min_quality_tier_id is None:
        return True
    if inst.quality_tier_id is None:
        return False
    return inst.quality_tier.sort_order >= requirement.min_quality_tier.sort_order


def gather_consumable_pks(
    *,
    available: Iterable[ItemInstance],
    requirements: Iterable[object],
) -> list[int]:
    """Validate that ``available`` satisfies ``requirements`` and return PKs to consume.

    For each requirement, scans ``available`` for instances matching the required
    item template and quality tier, sums their quantities, and greedily records
    the minimum set of PKs needed to cover the requirement.

    An instance PK already allocated to a prior requirement is excluded from
    consideration for later ones (prevents double-spending).

    Args:
        available: Iterable of ItemInstance-like objects to draw from.
        requirements: Iterable of requirement-like objects, each carrying
            ``item_template_id``, ``min_quality_tier_id``,
            ``min_quality_tier``, and ``quantity``.

    Returns:
        Flat list of ItemInstance PKs to pass to ``consume_pks``.

    Raises:
        InsufficientMaterials: On the first unsatisfied requirement.
            ``exc.requirement`` is the offending requirement object;
            ``exc.provided_qty`` is the total qualifying quantity found.
    """
    # Materialise available once so we can iterate it multiple times.
    available_list = list(available)
    consumed_pks: list[int] = []

    for req in requirements:
        # Candidates: right template, meets quality tier, not already allocated.
        candidates = [
            inst
            for inst in available_list
            if inst.template_id == req.item_template_id
            and meets_quality_tier(inst, req)
            and inst.pk not in consumed_pks
        ]

        total_qty = sum(inst.quantity for inst in candidates)
        if total_qty < req.quantity:
            raise InsufficientMaterials(requirement=req, provided_qty=total_qty)

        # Greedy: take instances in order until we've covered the requirement.
        remaining = req.quantity
        for inst in candidates:
            if remaining <= 0:
                break
            consumed_pks.append(inst.pk)
            remaining -= inst.quantity

    return consumed_pks


def consume_pks(pks: list[int]) -> None:
    """Delete ItemInstance rows identified by ``pks``.

    Args:
        pks: List of ItemInstance primary keys to delete. A no-op for an
            empty list (avoids a pointless DB round-trip).
    """
    if not pks:
        return
    ItemInstance.objects.filter(pk__in=pks).delete()
