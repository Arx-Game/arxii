"""Visibility computation for worn equipment — the look-output service.

Which of a character's worn items (and how much skin) an observer can see,
under the #2985 layer walk: plain cuts conceal beneath by default; a layer is
see-through by cut (``Silhouette.exposes_beneath``), material
(``ItemTemplate.is_revealing``), or being worn open (``EquippedItem.opened_at``
— the show verb). See ``world.items.services.visibility`` for the walk itself.

Layer hiding is bypassed for self-look and staff observers — see
``visible_worn_items_for`` for the contract.

The handler does the DB load on its first access for a given character;
this service runs zero queries thereafter. The handler's prefetch chain
covers ``item_instance.template.cached_slots``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from evennia.objects.models import ObjectDB

from core_management.permissions import is_staff_observer
from world.items.constants import EquipmentLayer
from world.items.services.visibility import is_see_through

if TYPE_CHECKING:
    from world.items.models import EquippedItem, ItemInstance

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

    Runs the #2985 layer walk over the cached ``EquippedItem`` rows: per
    region, the outermost layer shows; deeper layers show iff everything
    above them is see-through (cut / material / worn open).

    Layer hiding is bypassed when:
        - ``observer is character`` (looking at yourself), OR
        - ``observer`` is a staff user (via ``is_staff_observer``).

    ``observer=None`` (the default) applies hiding.
    """
    bypass_hiding = observer is character or is_staff_observer(observer)

    # Read from the cached equipment handler — one DB load per character on
    # first access, zero queries thereafter (Spec D §3.3).
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

    return [
        VisibleWornItem(
            item_instance=row.item_instance,
            body_region=row.body_region,
            equipment_layer=row.equipment_layer,
        )
        for row in rows
        if _slot_shows(rows, row)
    ]


def _slot_shows(rows: list[EquippedItem], row: EquippedItem) -> bool:
    """Whether this specific (region, layer) slot survives the walk."""
    rank = LAYER_RANK.get(row.equipment_layer, 99)
    return all(
        is_see_through(other)
        for other in rows
        if other.body_region == row.body_region and LAYER_RANK.get(other.equipment_layer, 99) > rank
    )


def covered_regions(character: ObjectDB) -> set[str]:
    """Body regions whose SKIN is covered (#2846/#2985).

    The layer walk reduced to its bottom: skin at a region is covered iff ANY
    worn layer there is not see-through — order doesn't matter for the bottom
    of the stack. The slit gown over stockings shows stockings (skin covered);
    over nothing, skin and its markings. Consumers: felt sun exposure
    (``world.species.sun_exposure``) and body-marking visibility
    (``world.forms.services.markings``). Zero queries — reads the cached
    equipment handler.
    """
    covered: set[str] = set()
    for row in character.equipped_items:
        if not is_see_through(row):
            covered.add(row.body_region)
    return covered
