"""Visibility computation for worn equipment.

The look-output service: which of a character's worn items are visible to
an observer. Reads from the cached ``character.equipped_items`` handler
(``CharacterEquipmentHandler``), applies per-(body_region, equipment_layer)
hiding via ``TemplateSlot.covers_lower_layers``.

Layer hiding is bypassed for self-look and staff observers - see
``visible_worn_items_for`` for the contract.

The handler does the DB load on its first access for a given character;
this service runs zero queries thereafter. The handler's prefetch chain
covers ``item_instance.template.cached_slots``, so ``_slot_for_row`` is
also free.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from evennia.objects.models import ObjectDB

from core_management.permissions import is_staff_observer
from world.items.constants import EquipmentLayer

if TYPE_CHECKING:
    from world.items.models import EquippedItem, ItemInstance, TemplateSlot


# Layer order from skin (lowest, closest to body) to accessory (highest).
LAYER_ORDER = (
    EquipmentLayer.SKIN.value,
    EquipmentLayer.UNDER.value,
    EquipmentLayer.BASE.value,
    EquipmentLayer.OVER.value,
    EquipmentLayer.OUTER.value,
    EquipmentLayer.ACCESSORY.value,
)
LAYER_RANK = {layer: idx for idx, layer in enumerate(LAYER_ORDER)}


@dataclass(frozen=True)
class VisibleWornItem:
    """One visible piece of a character's worn equipment."""

    item_instance: ItemInstance
    body_region: str
    equipment_layer: str


def visible_worn_items_for(
    character: ObjectDB,
    observer: object | None = None,
) -> list[VisibleWornItem]:
    """Return ``character``'s worn items visible to ``observer``.

    Walks ``EquippedItem`` rows for the character. For each body region,
    finds the highest layer whose ``TemplateSlot.covers_lower_layers`` is
    True; items at or above that layer are visible, items below are
    concealed.

    Layer hiding is bypassed when:
        - ``observer is character`` (looking at yourself), OR
        - ``observer`` is a staff user (via ``is_staff_observer``).

    ``observer=None`` (the default) applies hiding.
    """
    bypass_hiding = observer is character or is_staff_observer(observer)

    # Read from the cached equipment handler — one DB load per character on
    # first access, zero queries thereafter (Spec D §3.3). The handler's
    # prefetch chain covers ``item_instance.template.cached_slots`` so the
    # slot lookup in ``_slot_for_row`` is also free.
    rows = list(character.equipped_items)

    if not rows:
        return []

    if bypass_hiding:
        return [
            VisibleWornItem(
                item_instance=row.item_instance,
                body_region=row.body_region,
                equipment_layer=row.equipment_layer,
            )
            for row in rows
        ]

    # Group rows by body region.
    region_to_rows: dict[str, list[EquippedItem]] = {}
    for row in rows:
        region_to_rows.setdefault(row.body_region, []).append(row)

    visible: list[VisibleWornItem] = []
    for region_rows in region_to_rows.values():
        # Sort by layer rank (lowest to highest).
        region_rows.sort(key=lambda r: LAYER_RANK.get(r.equipment_layer, 99))

        # Find the index of the highest covering layer.
        cover_idx = -1
        for idx, row in enumerate(region_rows):
            slot = _slot_for_row(row)
            if slot is not None and slot.covers_lower_layers:
                cover_idx = idx  # highest wins (ascending iteration)

        # Items at or above the cover index are visible.
        # cover_idx == -1 means nothing covers; all visible.
        for idx, row in enumerate(region_rows):
            if idx >= cover_idx:
                visible.append(
                    VisibleWornItem(
                        item_instance=row.item_instance,
                        body_region=row.body_region,
                        equipment_layer=row.equipment_layer,
                    )
                )

    return visible


def covered_regions(character: ObjectDB) -> set[str]:
    """Body regions covered by an equipped non-revealing garment (#2846/#2985).

    THE skin-coverage predicate: skin at a region is covered iff ANY worn
    layer there conceals what lies beneath it — the top-down layer walk
    (#2985) reduced to an AND, since order doesn't matter for the bottom of
    the stack. A garment conceals unless its cut exposes beneath (the
    instance's effective silhouette's ``exposes_beneath`` — the crafter's
    pick at making; the slit gown over stockings shows stockings, over
    nothing shows skin) or its material does (``ItemTemplate.is_revealing``,
    a sheer lace veil). Either alone exposes the layer below.
    Consumers: felt sun exposure (``world.species.sun_exposure``) and
    body-marking visibility (``world.forms.services.markings``). Zero queries
    beyond warm FK caches — reads the cached equipment handler.
    """
    covered: set[str] = set()
    for row in character.equipped_items:
        instance = row.item_instance
        if instance.template.is_revealing:
            continue
        silhouette = instance.effective_silhouette
        if silhouette is not None and silhouette.exposes_beneath:
            continue
        covered.add(row.body_region)
    return covered


def _slot_for_row(row: EquippedItem) -> TemplateSlot | None:
    """Return the TemplateSlot for ``row``'s template at the row's region+layer."""
    template = row.item_instance.template
    slots = template.cached_slots
    for slot in slots:
        if slot.body_region == row.body_region and slot.equipment_layer == row.equipment_layer:
            return slot
    return None
