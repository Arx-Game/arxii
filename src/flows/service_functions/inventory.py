"""Inventory mutation service functions.

Used by both telnet commands and the WebSocket ``inventory_action``
inputfunc. All mutations run inside ``transaction.atomic`` so partial
failures roll back fully.
"""

from __future__ import annotations

from django.db import transaction

from flows.object_states.character_state import CharacterState
from flows.object_states.item_state import ItemState
from world.items.constants import OwnershipEventType
from world.items.exceptions import PermissionDenied
from world.items.models import EquippedItem, OwnershipEvent
from world.items.services import equip_item, unequip_item


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


@transaction.atomic
def give(
    giver: CharacterState,
    recipient: CharacterState,
    item: ItemState,
) -> None:
    """Transfer ``item`` from ``giver`` to ``recipient``.

    Writes an ``OwnershipEvent(GIVEN)`` row, transfers ``owner``, and
    moves the underlying ``ObjectDB`` to the recipient. Auto-unequips
    if the item is currently equipped.
    """
    if not item.can_give(giver=giver, recipient=recipient):
        raise PermissionDenied

    previous_owner = item.instance.owner
    # Snapshot rows before iteration — unequip_item deletes them as we go.
    for equipped in list(item.instance.equipped_slots.all()):
        unequip_item(equipped_item=equipped)

    item.instance.game_object.location = recipient.obj
    item.instance.game_object.save()
    item.instance.owner = recipient.obj.account
    item.instance.save(update_fields=["owner"])
    OwnershipEvent.objects.create(
        item_instance=item.instance,
        event_type=OwnershipEventType.GIVEN,
        from_account=previous_owner,
        to_account=recipient.obj.account,
    )


@transaction.atomic
def equip(character: CharacterState, item: ItemState) -> None:
    """Equip ``item`` on ``character`` in every slot its template declares.

    For each declared slot, if the same (body_region, equipment_layer) is
    already occupied on this character by a different item, that item is
    unequipped first (auto-swap). Different layers at the same body region
    are left alone. Multi-region items create one row per region atomically.
    """
    if not item.can_equip(wearer=character):
        raise PermissionDenied

    sheet = character.obj.sheet_data
    for slot in item.instance.template.cached_slots:
        existing = EquippedItem.objects.filter(
            character=character.obj,
            body_region=slot.body_region,
            equipment_layer=slot.equipment_layer,
        ).first()
        if existing is not None and existing.item_instance != item.instance:
            unequip_item(equipped_item=existing)
        equip_item(
            character_sheet=sheet,
            item_instance=item.instance,
            body_region=slot.body_region,
            equipment_layer=slot.equipment_layer,
        )
