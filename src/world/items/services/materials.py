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
  and ``.quantity``. A requirement may optionally expose
  ``.material_category_id``; when set (not None) it matches any instance
  whose ``template.material_category_id`` equals it, instead of matching by
  template. Callers must ``select_related("template")`` on ``available`` so
  the category walk stays query-free.

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


def _requirement_category_id(req: object) -> int | None:
    """Return ``req.material_category_id`` when the attribute exists and is set.

    Requirements without the attribute — e.g. RitualComponentRequirement — are
    template-mode, so they resolve to None and match by template. Resolved once
    per requirement (not per candidate) to keep the ritual path free of a
    per-instance AttributeError.
    """
    try:
        return req.material_category_id
    except AttributeError:
        return None


def _matches_requirement(inst: ItemInstance, req: object, category_id: int | None) -> bool:
    """True if ``inst`` satisfies ``req``.

    When ``category_id`` is set, any instance whose template belongs to that
    material category matches; otherwise the match is by template id.
    """
    if category_id is not None:
        return inst.template.material_category_id == category_id
    return inst.template_id == req.item_template_id


def gather_consumable_pks(
    *,
    available: Iterable[ItemInstance],
    requirements: Iterable[object],
) -> list[tuple[ItemInstance, int]]:
    """Validate that ``available`` satisfies ``requirements`` and return allocations.

    For each requirement, scans ``available`` for instances matching the required
    item template and quality tier, sums their quantities, and greedily records
    the minimum set of (instance, amount) pairs needed to cover the requirement
    exactly — a requirement of 1 against a stack of 5 returns ``[(inst, 1)]``,
    not the whole stack.

    An instance already allocated to a prior requirement is excluded from
    consideration for later ones (prevents double-spending).

    Args:
        available: Iterable of ItemInstance-like objects to draw from.
        requirements: Iterable of requirement-like objects, each carrying
            ``item_template_id``, ``min_quality_tier_id``,
            ``min_quality_tier``, and ``quantity``.

    Returns:
        List of ``(ItemInstance, amount)`` tuples to pass to ``consume_materials``.

    Raises:
        InsufficientMaterials: On the first unsatisfied requirement.
            ``exc.requirement`` is the offending requirement object;
            ``exc.provided_qty`` is the total qualifying quantity found.
    """
    # Materialise available once so we can iterate it multiple times.
    available_list = list(available)
    consumed: list[tuple[ItemInstance, int]] = []
    allocated_pks: set[int] = set()

    for req in requirements:
        # Candidates: right template (or material category), meets quality tier,
        # not already allocated. Category resolved once per requirement.
        category_id = _requirement_category_id(req)
        candidates = [
            inst
            for inst in available_list
            if _matches_requirement(inst, req, category_id)
            and meets_quality_tier(inst, req)
            and inst.pk not in allocated_pks
        ]

        total_qty = sum(inst.quantity for inst in candidates)
        if total_qty < req.quantity:
            raise InsufficientMaterials(requirement=req, provided_qty=total_qty)

        # Greedy: take instances in order until we've covered the requirement.
        remaining = req.quantity
        for inst in candidates:
            if remaining <= 0:
                break
            take = min(inst.quantity, remaining)
            consumed.append((inst, take))
            allocated_pks.add(inst.pk)
            remaining -= take

    return consumed


def consume_materials(allocations: list[tuple[ItemInstance, int]]) -> None:
    """Decrement quantity on each allocated ItemInstance, deleting depleted rows.

    Follows the codebase's canonical SharedMemoryModel mutation pattern (ADR-0008):
    mutate the Python attribute, then ``.save(update_fields=)`` or ``.delete()``.
    Never uses ``F("quantity") - n`` with ``.update()`` — that would leave
    in-memory cached instances stale.

    Args:
        allocations: List of ``(ItemInstance, amount)`` tuples from
            ``gather_consumable_pks``. A no-op for an empty list.
    """
    if not allocations:
        return
    from django.db import transaction  # noqa: PLC0415

    with transaction.atomic():
        for inst, amount in allocations:
            inst.quantity -= amount
            if inst.quantity <= 0:
                inst.delete()
            else:
                inst.save(update_fields=["quantity"])
