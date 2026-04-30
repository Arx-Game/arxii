"""Inventory mutation service functions.

Used by both telnet commands and the WebSocket ``inventory_action``
inputfunc. All mutations run inside ``transaction.atomic`` so partial
failures roll back fully.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from django.db import transaction

from flows.object_states.character_state import CharacterState
from flows.object_states.item_state import ItemState
from world.items.exceptions import PermissionDenied

if TYPE_CHECKING:
    from world.items.models import ItemInstance


@transaction.atomic
def pick_up(character: CharacterState, item: ItemState) -> None:
    """Move ``item`` from its current location into ``character``'s possession.

    If the item is currently unowned (``owner`` is null), ``character``'s
    account becomes the owner. Pre-existing ownership is preserved.
    """
    if not item.can_take(taker=character):
        raise PermissionDenied
    instance = cast("ItemInstance", item.obj)
    instance.game_object.location = character.obj
    instance.game_object.save()
    if instance.owner is None:
        instance.owner = character.obj.account
        instance.save(update_fields=["owner"])
