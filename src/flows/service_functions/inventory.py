"""Inventory mutation service functions.

Used by both telnet commands and the WebSocket ``inventory_action``
inputfunc. All mutations run inside ``transaction.atomic`` so partial
failures roll back fully.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from flows.object_states.character_state import CharacterState
from flows.object_states.item_state import ItemState
from world.items.constants import OwnershipEventType
from world.items.exceptions import (
    ContainerAccessDenied,
    ContainerClosed,
    ContainerFull,
    ItemTooLarge,
    NoDropLocation,
    NotAContainer,
    NotEquipped,
    NotInContainer,
    NotInPossession,
    NotReachable,
    OwnedByAnother,
    RecipientNotAdjacent,
)
from world.items.models import EquippedItem, OwnershipEvent
from world.items.services import equip_item, unequip_item

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.items.models import ItemInstance
    from world.roster.models import RosterTenure


def _active_tenure_for_sheet(sheet: CharacterSheet) -> RosterTenure | None:
    """Return ``sheet``'s active ``RosterTenure`` (end_date null), or None for NPCs (#1909).

    Mirrors the dispatch layer's sheet→active-tenure resolution
    (``actions.player_interface``). An NPC-owned sheet has no live tenure.
    """
    from world.roster.models import RosterTenure  # noqa: PLC0415

    return RosterTenure.objects.filter(
        roster_entry__character_sheet=sheet,
        end_date__isnull=True,
    ).first()


def _container_policy_denies(taker_sheet: CharacterSheet, container_instance: ItemInstance) -> bool:
    """True when the container's access policy bars ``taker_sheet`` from its contents.

    Only the IMMEDIATE ``contained_in`` container's policy governs — no ancestor
    chaining up nested containers (per the #1909 spec).
    """
    from world.items.constants import ContainerAccessPolicy  # noqa: PLC0415

    owner_sheet = container_instance.holder_character_sheet
    policy = container_instance.access_policy
    if policy == ContainerAccessPolicy.OPEN or owner_sheet is None:
        return False
    if owner_sheet.pk == taker_sheet.pk:
        return False
    if policy == ContainerAccessPolicy.OWNER_ONLY:
        return True
    # FRIENDS: resolve both sides to active tenures; NPC sides have none → deny.
    owner_tenure = _active_tenure_for_sheet(owner_sheet)
    taker_tenure = _active_tenure_for_sheet(taker_sheet)
    if owner_tenure is None or taker_tenure is None:
        return True
    from world.scenes.friend_services import is_friend  # noqa: PLC0415

    return not is_friend(owner_tenure=owner_tenure, friend_tenure=taker_tenure)


def take_requires_steal(taker_sheet: CharacterSheet | None, item_instance: ItemInstance) -> bool:
    """The one ownership/policy test (#1909): True → only ``steal`` may move it.

    Room item owned by someone else → steal. Container item: the container's
    policy decides; policy pass → plain take even if the item belongs to the
    container's owner (sanctioned borrowing).
    """
    if taker_sheet is None:
        # Sheet-less actors (GM/staff/companion tooling) keep legacy free-take
        # behavior — theft consequence machinery is sheet-anchored and cannot
        # apply to them.
        return False
    container = item_instance.contained_in
    if container is not None:
        return _container_policy_denies(taker_sheet, container)
    owner = item_instance.holder_character_sheet
    return owner is not None and owner.pk != taker_sheet.pk


def _fire_item_acquisition_triggers(acquirer: CharacterState, item: ItemState) -> None:
    """Fire passive item-acquisition clue triggers for ``acquirer`` after commit (#1160).

    Scheduled with ``transaction.on_commit`` so the transfer is durable first and a trigger
    hiccup can never roll it back; wrapped in ``run_safely`` so a failure is captured for
    staff (not swallowed) without surfacing as a broken give/pick-up. The clue service's own
    cheap "any triggers for this kind?" query short-circuits ordinary items.
    """
    character_obj = acquirer.obj
    instance = item.instance

    def _run() -> None:
        from world.clues.services import maybe_grant_item_acquisition_clues  # noqa: PLC0415
        from world.player_submissions.services import run_safely  # noqa: PLC0415

        run_safely(
            "item_acquisition_clue_triggers",
            lambda: maybe_grant_item_acquisition_clues(character_obj, instance),
            actor=character_obj,
        )

    transaction.on_commit(_run)


@transaction.atomic
def pick_up(character: CharacterState, item: ItemState) -> None:
    """Move ``item`` from its current location into ``character``'s possession.

    If the item is currently unowned (``holder_character_sheet`` is null),
    ``character``'s body (CharacterSheet) becomes the holder. Pre-existing
    ownership is preserved. If the item is in an open container in the
    room, ``contained_in`` is cleared so the item ends up plainly in the
    character's inventory.

    The #1909 ownership/policy gate runs before any mutation: a room item
    owned by someone else raises ``OwnedByAnother``; a container item barred
    by the container's access policy raises ``ContainerAccessDenied``. Steal
    (a later task) is the deliberate bypass.
    """
    if not item.can_take(taker=character):
        raise NotReachable
    taker_sheet = getattr(character.obj, "sheet_data", None)  # noqa: GETATTR_LITERAL
    if take_requires_steal(taker_sheet, item.instance):
        if item.instance.contained_in is not None:
            raise ContainerAccessDenied
        raise OwnedByAnother
    if item.instance.contained_in is not None:
        item.instance.contained_in = None
        item.instance.save(update_fields=["contained_in"])
    previous_location = item.instance.game_object.location
    if not item.instance.game_object.move_to(character.obj, quiet=True):
        raise NotReachable
    # Sheet-less actors can't own things — skip the assignment (holder stays None).
    if item.instance.holder_character_sheet_id is None and taker_sheet is not None:
        item.instance.holder_character_sheet = taker_sheet
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
    _fire_item_acquisition_triggers(character, item)


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
    _fire_item_acquisition_triggers(recipient, item)


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

    The #1909 gate runs before any mutation: if the container's access
    policy bars this taker, raises ``ContainerAccessDenied``. Steal (a
    later task) is the deliberate bypass.
    """
    if not item.can_take(taker=character):
        raise NotReachable
    if item.instance.contained_in is None:
        raise NotInContainer
    taker_sheet = getattr(character.obj, "sheet_data", None)  # noqa: GETATTR_LITERAL
    if take_requires_steal(taker_sheet, item.instance):
        raise ContainerAccessDenied
    item.instance.contained_in = None
    item.instance.save(update_fields=["contained_in"])
    if not item.instance.game_object.move_to(character.obj, quiet=True):
        raise NotReachable
    # Item now located on character — invalidate so the next read sees it.
    character.obj.carried_items.invalidate()
