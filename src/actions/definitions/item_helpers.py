"""Shared helpers for item-related actions.

Resolve an explicitly typed ItemInstance or a legacy ObjectDB target to the
item used by inventory services. Resolution does not grant permission to act.
"""

from __future__ import annotations

from evennia.objects.models import ObjectDB

from world.items.models import ItemInstance


def resolve_item_instance(target: ObjectDB | ItemInstance | None) -> ItemInstance | None:
    """Return the item represented by an explicitly typed target.

    This helper does not resolve integer IDs or authorize an operation.

    Args:
        target: A resolved object, an item instance, or no target.

    Returns:
        The explicit item or the object's related item, otherwise None.
    """
    if isinstance(target, ItemInstance):
        return target
    if not isinstance(target, ObjectDB):
        return None
    try:
        return target.item_instance
    except ObjectDB.item_instance.RelatedObjectDoesNotExist:  # type: ignore[attr-defined]
        return None
