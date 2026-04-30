"""Shared helpers for item-related actions.

These helpers bridge the actions layer (which receives ``ObjectDB`` targets)
to the ``world.items`` domain models that inventory service functions operate
on.
"""

from __future__ import annotations

from evennia.objects.models import ObjectDB

from world.items.models import ItemInstance


def resolve_item_instance(target: ObjectDB) -> ItemInstance | None:
    """Return the ``ItemInstance`` linked to ``target``, or ``None`` if none exists.

    The actions layer accepts an ``ObjectDB`` as the target, but the inventory
    service functions operate on ``ItemInstance``. This bridges the two via
    the ``OneToOneField`` reverse accessor, returning ``None`` for plain
    ObjectDBs that have no ItemInstance row (e.g. NPCs picked up by mistake).
    """
    try:
        return target.item_instance
    except ObjectDB.item_instance.RelatedObjectDoesNotExist:  # type: ignore[attr-defined]
        return None
