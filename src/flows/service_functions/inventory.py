"""Inventory mutation service functions.

Used by both telnet commands and the WebSocket ``inventory_action``
inputfunc. All mutations run inside ``transaction.atomic`` so partial
failures roll back fully.
"""

from __future__ import annotations

from django.db import transaction

from flows.object_states.character_state import CharacterState
from flows.object_states.item_state import ItemState
from world.items.exceptions import PermissionDenied
from world.items.services import unequip_item


@transaction.atomic
def pick_up(character: CharacterState, item: ItemState) -> None:
    """Move ``item`` from its current location into ``character``'s possession.

    If the item is currently unowned (``owner`` is null), ``character``'s
    account becomes the owner. Pre-existing ownership is preserved.
    """
    if not item.can_take(taker=character):
        raise PermissionDenied
    item.instance.game_object.location = character.obj
    item.instance.game_object.save()
    if item.instance.owner is None:
        item.instance.owner = character.obj.account
        item.instance.save(update_fields=["owner"])


@transaction.atomic
def drop(character: CharacterState, item: ItemState) -> None:
    """Move ``item`` from ``character``'s possession into their current room.

    If the item is currently equipped, all ``EquippedItem`` rows are
    removed first via ``world.items.services.unequip_item`` so the
    character's cached equipment handler is invalidated correctly.
    """
    if not item.can_drop(dropper=character):
        raise PermissionDenied
    # Snapshot rows before iteration — unequip_item deletes them as we go.
    for equipped in list(item.instance.equipped_slots.all()):
        unequip_item(equipped_item=equipped)
    item.instance.game_object.location = character.obj.location
    item.instance.game_object.save()
