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
from world.items.exceptions import (
    ContainerClosed,
    ContainerFull,
    ItemTooLarge,
    NoDropLocation,
    NotAContainer,
    NotEquipped,
    NotInContainer,
    NotInPossession,
    NotReachable,
    RecipientNotAdjacent,
)
from world.items.models import EquippedItem, OwnershipEvent
from world.items.services import equip_item, unequip_item


@transaction.atomic
def pick_up(character: CharacterState, item: ItemState) -> None:
    """Move ``item`` from its current location into ``character``'s possession.

    If the item is currently unowned (``owner`` is null), ``character``'s
    account becomes the owner. Pre-existing ownership is preserved. If the
    item is in an open container in the room, ``contained_in`` is cleared
    so the item ends up plainly in the character's inventory.
    """
    if not item.can_take(taker=character):
        raise NotReachable
    if item.instance.contained_in is not None:
        item.instance.contained_in = None
        item.instance.save(update_fields=["contained_in"])
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
    character's cached equipment handler is invalidated correctly. If the
    item is in a container in the character's inventory, ``contained_in``
    is cleared as part of the drop.
    """
    if not item.can_drop(dropper=character):
        raise NotInPossession
    if character.obj.location is None:
        raise NoDropLocation
    if item.instance.contained_in is not None:
        item.instance.contained_in = None
        item.instance.save(update_fields=["contained_in"])
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
        raise NotInPossession
    if recipient.obj.location != giver.obj.location:
        raise RecipientNotAdjacent

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
        raise NotInPossession

    sheet = character.obj.sheet_data
    for slot in item.instance.template.cached_slots:
        existing = EquippedItem.objects.filter(
            character=character.obj,
            body_region=slot.body_region,
            equipment_layer=slot.equipment_layer,
        ).first()
        if existing is not None:
            if existing.item_instance == item.instance:
                # Already equipped here — re-equip is a silent no-op.
                continue
            unequip_item(equipped_item=existing)
        equip_item(
            character_sheet=sheet,
            item_instance=item.instance,
            body_region=slot.body_region,
            equipment_layer=slot.equipment_layer,
        )


@transaction.atomic
def unequip(character: CharacterState, item: ItemState) -> None:
    """Remove all ``EquippedItem`` rows for ``item`` on ``character``.

    Raises ``NotEquipped`` if the item has no equipped rows. The item
    stays in the character's inventory — its underlying ``ObjectDB``
    location is unchanged.
    """
    # Snapshot rows before iteration — unequip_item deletes them as we go.
    equipped_rows = list(item.instance.equipped_slots.filter(character=character.obj))
    if not equipped_rows:
        raise NotEquipped
    for row in equipped_rows:
        unequip_item(equipped_item=row)


@transaction.atomic
def put_in(
    character: CharacterState,
    item: ItemState,
    container: ItemState,
) -> None:
    """Move ``item`` into ``container`` (an item that is itself a container).

    Validates the container is reachable by ``character``, the container's
    template/state, and the item's possession by ``character``. Sets
    ``item.contained_in = container``. Does NOT change the item's underlying
    ObjectDB location — the container still lives in the character's
    inventory; the item lives "inside" via the FK.
    """
    if not container.is_reachable_by(character.obj):
        raise NotReachable
    container_template = container.instance.template
    if not container_template.is_container:
        raise NotAContainer
    if container_template.supports_open_close and not container.instance.is_open:
        raise ContainerClosed
    if (
        container_template.container_capacity
        and container.instance.contents.count() >= container_template.container_capacity
    ):
        raise ContainerFull
    if (
        container_template.container_max_item_size
        and item.instance.template.size > container_template.container_max_item_size
    ):
        raise ItemTooLarge
    if item.instance.game_object.location != character.obj:
        raise NotInPossession

    item.instance.contained_in = container.instance
    item.instance.save(update_fields=["contained_in"])


@transaction.atomic
def take_out(character: CharacterState, item: ItemState) -> None:
    """Move ``item`` out of its container into ``character``'s possession.

    Validates the item is reachable (which walks the container chain and
    rejects closed containers) and that it actually has a ``contained_in``
    set. Clears ``contained_in`` and moves the underlying ``ObjectDB`` to
    the character.
    """
    if not item.can_take(taker=character):
        raise NotReachable
    if item.instance.contained_in is None:
        raise NotInContainer
    item.instance.contained_in = None
    item.instance.save(update_fields=["contained_in"])
    item.instance.game_object.location = character.obj
    item.instance.game_object.save()
