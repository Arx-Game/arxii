"""Phase F — Items polish + fashion flow (#676).

Three event hooks + one recompute:

* ``place_item_in_room(item_instance, room, persona)`` — creates a
  RoomItem placement record, flows polish into RoomPolish (which
  credits tenant + rolls up to building owner via
  ``apply_room_polish_delta``).
* ``remove_item_from_room(item_instance)`` — reverses the placement
  and subtracts the polish.
* ``recompute_persona_prestige_from_items(persona)`` — sums
  ``polish_value`` of every item currently equipped on the persona's
  body. Reads through ``EquippedItem.character`` (Evennia ObjectDB
  side). Returns the new value.

Mutual exclusivity: place/equip are XOR. Placement is gated by
``EquippedItem.objects.filter(item_instance=...).exists()``; equipping
checks the reverse. Returns False on conflict rather than raising — the
service-layer caller turns this into a user-facing message.
"""

from __future__ import annotations

import logging

from django.db import transaction

from evennia_extensions.models import RoomProfile
from world.buildings.polish_services import apply_room_polish_delta
from world.items.models import EquippedItem, ItemInstance, RoomItem
from world.scenes.models import Persona

logger = logging.getLogger(__name__)


@transaction.atomic
def place_item_in_room(
    item_instance: ItemInstance,
    room: RoomProfile,
    persona: Persona | None = None,
) -> RoomItem | None:
    """Place ``item_instance`` as decor in ``room``.

    Returns the created RoomItem, or None when the item is currently
    equipped (the XOR rule). Idempotent on the same placement: if the
    item is already placed in this room, returns the existing row.

    XOR race-safety: locks ``item_instance`` for the duration of this
    transaction so concurrent place/equip attempts on the same item
    serialize. Without this lock, two callers could both pass their
    "is the other state set?" check and both create rows.
    """
    # Lock the item row first — any concurrent place or equip on this
    # same item now blocks until this transaction commits.
    ItemInstance.objects.select_for_update().get(pk=item_instance.pk)

    if EquippedItem.objects.filter(item_instance=item_instance).exists():
        return None

    existing = RoomItem.objects.filter(item_instance=item_instance).first()
    if existing is not None:
        if existing.room_id == room.pk:
            return existing
        # Moving from another room: subtract the old polish first.
        _flow_item_polish(item_instance, existing.room, delta_sign=-1)
        existing.delete()

    placement = RoomItem.objects.create(
        room=room,
        item_instance=item_instance,
        placed_by_persona=persona,
    )
    _flow_item_polish(item_instance, room, delta_sign=1)
    return placement


@transaction.atomic
def remove_item_from_room(item_instance: ItemInstance) -> bool:
    """Reverse ``place_item_in_room``. Returns True iff there was a placement."""
    placement = RoomItem.objects.filter(item_instance=item_instance).first()
    if placement is None:
        return False
    _flow_item_polish(item_instance, placement.room, delta_sign=-1)
    placement.delete()
    return True


def _flow_item_polish(item_instance: ItemInstance, room: RoomProfile, *, delta_sign: int) -> None:
    """Apply (or reverse) this item's polish contribution to the room."""
    template = item_instance.template
    if template.polish_value <= 0 or template.polish_category_id is None:
        return
    apply_room_polish_delta(
        room=room,
        category=template.polish_category,
        delta=delta_sign * template.polish_value,
    )


def recompute_persona_prestige_from_items(persona: Persona) -> int:
    """Sum equipped-item polish into the persona's prestige_from_items.

    Reads ``EquippedItem`` rows on the persona's character (body), sums
    each item's ``template.polish_value``. Writes through to the persona
    and updates ``total_prestige``.

    Body-keyed equipment (per #684) means all equipped items on the body
    are visible regardless of currently-presented persona — but only the
    persona currently being presented is credited. Callers (persona-
    switch event hook, equip/unequip hook) determine *which* persona to
    recompute; this function just reads the body.
    """
    sheet = persona.character_sheet
    if sheet is None or sheet.character_id is None:
        return persona.prestige_from_items
    total = 0
    equipped = EquippedItem.objects.filter(character_id=sheet.character_id).select_related(
        "item_instance__template"
    )
    for slot in equipped:
        template = slot.item_instance.template
        if template.polish_value > 0 and template.polish_category_id is not None:
            total += template.polish_value
    if total == persona.prestige_from_items:
        return total
    persona.prestige_from_items = total
    persona.total_prestige = (
        persona.prestige_from_dwellings
        + persona.prestige_from_items
        + persona.prestige_from_orgs
        + persona.prestige_from_deeds
    )
    persona.save(update_fields=["prestige_from_items", "total_prestige"])
    return total


def can_equip_item(item_instance: ItemInstance) -> bool:
    """XOR gate the equipment service should consult before equipping.

    Returns False iff the item is currently placed in a room (must be
    removed first). True otherwise (including for items neither placed
    nor equipped).
    """
    return not RoomItem.objects.filter(item_instance=item_instance).exists()
