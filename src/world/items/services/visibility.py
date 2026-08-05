"""Worn-item visibility: the top-down layer walk (#2985, superseding #2965).

Apostate's ruling (2026-08-05): plain cuts CONCEAL what lies beneath them by
default; exposure is authored or performed. A worn layer is *see-through* when
any of three inputs says so:

- **cut** — the instance's effective silhouette has ``exposes_beneath``
  (the slit gown shows the stockings, or the skin when nothing is under);
- **material** — the template is ``is_revealing`` (sheer lace);
- **worn open** — ``EquippedItem.opened_at`` set by the show verb.

Per region, the outermost layer always shows; each deeper layer shows iff every
layer above it is see-through; skin (and its markings) shows iff ALL layers are
— one rule, three inputs, no per-slot covers flag and no state on the hidden
thing. Wearer-facing effects (comfort, armor, mitigation) never read this —
they read everything worn.

Operates purely on prefetched ``EquippedItem`` rows (with
``item_instance__template`` selected and the template's ``cached_slots``
prefetched) — no queries of its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from world.items.constants import EquipmentLayer

if TYPE_CHECKING:
    from collections.abc import Iterable

    from world.items.models import EquippedItem

_LAYER_ORDER: dict[str, int] = {
    EquipmentLayer.SKIN: 0,
    EquipmentLayer.UNDER: 1,
    EquipmentLayer.BASE: 2,
    EquipmentLayer.OVER: 3,
    EquipmentLayer.OUTER: 4,
    EquipmentLayer.ACCESSORY: 5,
}


def is_see_through(row: EquippedItem) -> bool:
    """Whether this worn row exposes what lies beneath it (#2985).

    Cut, material, or worn-open — any one suffices. THE single predicate the
    layer walk, the skin/coverage read, and the show/conceal verbs all share.
    ACCESSORY-layer pieces (jewelry, scarves, trims) never conceal beneath —
    they adorn a region, they don't blanket it; anything veil-like enough to
    hide things is authored as a garment layer.
    """
    if row.equipment_layer == EquipmentLayer.ACCESSORY:
        return True
    if row.opened_at is not None:
        return True
    instance = row.item_instance
    if instance.template.is_revealing:
        return True
    silhouette = instance.effective_silhouette
    return silhouette is not None and silhouette.exposes_beneath


@dataclass(frozen=True)
class WornVisibility:
    """Per-instance visibility over one equipment snapshot."""

    # instance_id -> number of its occupied region-slots an observer can see
    # (0 = fully concealed).
    visible_slot_counts: dict[int, int]
    # instance_id -> total occupied region-slots (the coverage weight).
    occupied_slot_counts: dict[int, int]

    def is_visible(self, instance_id: int) -> bool:
        return self.visible_slot_counts.get(instance_id, 0) > 0


def compute_worn_visibility(equipped_rows: Iterable[EquippedItem]) -> WornVisibility:
    """Resolve which worn pieces (and how many of their slots) are visible.

    The top-down walk per region: the outermost layer always shows; each
    deeper layer shows iff every layer above it at that region is
    see-through (``is_see_through`` — cut, material, or worn open).
    """
    rows = list(equipped_rows)
    by_region: dict[str, list[EquippedItem]] = {}
    for row in rows:
        by_region.setdefault(row.body_region, []).append(row)

    visible: dict[int, int] = {}
    occupied: dict[int, int] = {}

    for region_rows in by_region.values():
        # Outermost first.
        region_rows.sort(key=lambda r: _LAYER_ORDER.get(r.equipment_layer, 99), reverse=True)
        walk_open = True
        for row in region_rows:
            occupied[row.item_instance_id] = occupied.get(row.item_instance_id, 0) + 1
            if walk_open:
                visible[row.item_instance_id] = visible.get(row.item_instance_id, 0) + 1
                walk_open = is_see_through(row)

    return WornVisibility(visible_slot_counts=visible, occupied_slot_counts=occupied)
