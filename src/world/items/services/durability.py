"""Service: durability decrement on item instances (issue #508)."""

from __future__ import annotations

import contextlib

from django.db import transaction

from world.items.constants import OwnershipEventType
from world.items.models import EquippedItem, ItemInstance, OwnershipEvent


@transaction.atomic
def decrement_item_durability(*, item_instance: ItemInstance, amount: int = 1) -> ItemInstance:
    """Reduce ``item_instance.durability`` by ``amount`` (clamped at 0).

    No-op when the item is not durability-tracked (``durability is None``).
    On reaching 0, logs an ``OwnershipEventType.CONSUMED`` ledger row. Invalidates
    the effective-stat caches and every wearer's equipment handler.
    """
    if item_instance.durability is None or amount <= 0:
        return item_instance

    was_broken = item_instance.durability == 0
    item_instance.durability = max(0, item_instance.durability - amount)
    item_instance.save(update_fields=["durability"])

    for attr in ("effective_weapon_damage", "effective_armor_soak"):
        with contextlib.suppress(AttributeError):
            delattr(item_instance, attr)

    for equipped in EquippedItem.objects.filter(item_instance=item_instance):
        equipped.character.equipped_items.invalidate()

    if item_instance.durability == 0 and not was_broken:
        OwnershipEvent.objects.create(
            item_instance=item_instance,
            event_type=OwnershipEventType.CONSUMED,
            notes="Durability depleted — item broke from use.",
        )
    return item_instance
