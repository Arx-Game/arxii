"""Items service functions — public API."""

from world.items.services.appearance import VisibleWornItem, visible_worn_items_for
from world.items.services.equip import equip_item, unequip_item
from world.items.services.facets import attach_facet_to_item, remove_facet_from_item

__all__ = [
    "VisibleWornItem",
    "attach_facet_to_item",
    "equip_item",
    "remove_facet_from_item",
    "unequip_item",
    "visible_worn_items_for",
]
