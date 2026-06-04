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

    If the item is currently unowned (``holder_character_sheet`` is null),
    ``character``'s body (CharacterSheet) becomes the holder. Pre-existing
    ownership is preserved. If the item is in an open container in the
    room, ``contained_in`` is cleared so the item ends up plainly in the
    character's inventory.
    """
    if not item.can_take(taker=character):
        raise NotReachable
    if item.instance.contained_in is not None:
        item.instance.contained_in = None
        item.instance.save(update_fields=["contained_in"])
    previous_location = item.instance.game_object.location
    if not item.instance.game_object.move_to(character.obj, quiet=True):
        raise NotReachable
    if item.instance.holder_character_sheet_id is None:
        item.instance.holder_character_sheet = character.obj.sheet_data
        item.instance.save(update_fields=["holder_character_sheet"])
    character.obj.carried_items.invalidate()
    # If the item came from another character (rare), invalidate that too.
    # Rooms/containers don't have ``carried_items`` — only characters do.
    if (
        previous_location is not None
        and previous_location.pk != character.obj.pk
        and hasattr(previous_location, "carried_items")
    ):
        previous_location.carried_items.invalidate()


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
    if not item.instance.game_object.move_to(character.obj.location, quiet=True):
        raise NotReachable
    character.obj.carried_items.invalidate()


@transaction.atomic
def give(
    giver: CharacterState,
    recipient: CharacterState,
    item: ItemState,
) -> None:
    """Transfer ``item`` from ``giver`` to ``recipient``.

    Writes an ``OwnershipEvent(GIVEN)`` row, transfers the holder
    (CharacterSheet — the body), and moves the underlying ``ObjectDB``
    to the recipient. Auto-unequips if the item is currently equipped.
    The OwnershipEvent also snapshots each side's presented persona for
    IC-narrative purposes; the audit truth is the CharacterSheet pair.
    """
    if not item.can_give(giver=giver, recipient=recipient):
        raise NotInPossession
    if recipient.obj.location != giver.obj.location:
        raise RecipientNotAdjacent

    previous_holder_sheet = item.instance.holder_character_sheet
    # Snapshot rows before iteration — unequip_item deletes them as we go.
    for equipped in list(item.instance.equipped_slots.all()):
        unequip_item(equipped_item=equipped)

    if not item.instance.game_object.move_to(recipient.obj, quiet=True):
        raise NotReachable
    recipient_sheet = recipient.obj.sheet_data
    item.instance.holder_character_sheet = recipient_sheet
    item.instance.save(update_fields=["holder_character_sheet"])
    # Snapshot the IC face each side is wearing at the transfer moment.
    # Null falls back to the sheet's primary_persona at render time.
    giver_persona = (
        previous_holder_sheet.primary_persona if previous_holder_sheet is not None else None
    )
    OwnershipEvent.objects.create(
        item_instance=item.instance,
        event_type=OwnershipEventType.GIVEN,
        from_character_sheet=previous_holder_sheet,
        to_character_sheet=recipient_sheet,
        from_persona_display=giver_persona,
        to_persona_display=recipient_sheet.primary_persona,
    )
    giver.obj.carried_items.invalidate()
    recipient.obj.carried_items.invalidate()


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
    ``item.contained_in = container`` and moves the underlying ``ObjectDB``
    into the container's ``ObjectDB`` so Evennia's ``look``/contents traversal
    sees the item as being inside the container.
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
    if not item.instance.game_object.move_to(container.instance.game_object, quiet=True):
        raise NotReachable
    # Item moved off the character (now nested in the container's game_object),
    # so the carried-items cache for the character is stale.
    character.obj.carried_items.invalidate()


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
    if not item.instance.game_object.move_to(character.obj, quiet=True):
        raise NotReachable
    # Item now located on character — invalidate so the next read sees it.
    character.obj.carried_items.invalidate()
