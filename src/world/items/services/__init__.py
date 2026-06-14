"""Items service functions — public API."""

from world.items.services.appearance import VisibleWornItem, visible_worn_items_for
from world.items.services.equip import equip_item, unequip_item
from world.items.services.facets import attach_facet_to_item, remove_facet_from_item
from world.items.services.mantle import (
    get_max_cleared_mantle_level,
    grant_mantle_clearance,
    record_mantle_clearances,
)

__all__ = [
    "VisibleWornItem",
    "attach_facet_to_item",
    "equip_item",
    "get_max_cleared_mantle_level",
    "grant_mantle_clearance",
    "record_mantle_clearances",
    "remove_facet_from_item",
    "unequip_item",
    "visible_worn_items_for",
]
