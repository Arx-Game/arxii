"""Worn-item visibility (#2965): what observers can actually see.

Apostate's coverage/concealment ruling: social-facing effects (accents,
prestige) read only VISIBLE pieces; wearer-facing effects (comfort, armor,
mitigation) always read everything worn; LEGEND pierces concealment (it is
magical — ownership carries it). A piece is visible iff at least one of the
body-region slots it occupies is not covered by a ``covers_lower_layers``
slot on a higher layer at the same region — or it has been deliberately
REVEALED (``EquippedItem.revealed_at``; the state dies naturally with the
row on unequip).

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


@dataclass(frozen=True)
class WornVisibility:
    """Per-instance visibility over one equipment snapshot."""

    # instance_id -> number of its occupied region-slots an observer can see
    # (0 = fully concealed). Revealed pieces count ALL their occupied slots.
    visible_slot_counts: dict[int, int]
    # instance_id -> total occupied region-slots (the coverage weight).
    occupied_slot_counts: dict[int, int]

    def is_visible(self, instance_id: int) -> bool:
        return self.visible_slot_counts.get(instance_id, 0) > 0


def _covers(row: EquippedItem) -> bool:
    """Whether this equipped row's slot hides lower layers at its region."""
    for slot in row.item_instance.template.cached_slots:
        if slot.body_region == row.body_region and slot.equipment_layer == row.equipment_layer:
            return bool(slot.covers_lower_layers)
    return False


def compute_worn_visibility(equipped_rows: Iterable[EquippedItem]) -> WornVisibility:
    """Resolve which worn pieces (and how many of their slots) are visible.

    A row is concealed when any row at the SAME body region on a HIGHER
    layer covers lower layers. A revealed piece (``revealed_at`` set) counts
    every slot it occupies regardless of covering — the drama of the reveal
    is that the concealed thing now openly counts.
    """
    rows = list(equipped_rows)
    by_region: dict[str, list[EquippedItem]] = {}
    for row in rows:
        by_region.setdefault(row.body_region, []).append(row)

    revealed_ids = {row.item_instance_id for row in rows if row.revealed_at is not None}
    visible: dict[int, int] = {}
    occupied: dict[int, int] = {}

    for region_rows in by_region.values():
        covering_orders = [
            _LAYER_ORDER.get(row.equipment_layer, 0) for row in region_rows if _covers(row)
        ]
        for row in region_rows:
            occupied[row.item_instance_id] = occupied.get(row.item_instance_id, 0) + 1
            order = _LAYER_ORDER.get(row.equipment_layer, 0)
            concealed = any(cover > order for cover in covering_orders)
            if not concealed:
                visible[row.item_instance_id] = visible.get(row.item_instance_id, 0) + 1

    for instance_id in revealed_ids:
        visible[instance_id] = occupied.get(instance_id, 0)

    return WornVisibility(visible_slot_counts=visible, occupied_slot_counts=occupied)
