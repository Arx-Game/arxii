"""Outfit-related service functions.

The action-layer entry points (called from the action layer for IC actions
that have game-state consequences). Save / delete / slot-edit services
live alongside but are called from the REST layer for player bookkeeping.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from flows.object_states.character_state import CharacterState
from flows.object_states.item_state import ItemState
from flows.object_states.outfit_state import OutfitState
from flows.service_functions.inventory import equip, unequip
from world.items.exceptions import NotAContainer, NotReachable, PermissionDenied, SlotIncompatible
from world.items.models import EquippedItem, ItemInstance, Outfit, OutfitSlot

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet


@transaction.atomic
def apply_outfit(character: CharacterState, outfit_state: OutfitState) -> None:
    """Equip all of ``outfit_state``'s pieces atomically.

    Slots not specified by the outfit are left as-is (no clean-strip). Items
    already equipped at the same (region, layer) are auto-swapped via the
    existing ``equip()`` policy. If any item is missing or unreachable, the
    whole transaction rolls back and raises.

    Validation order (raises on first failure):
        1. Outfit's character_sheet matches the actor → PermissionDenied
        2. Wardrobe is reachable by the actor → NotReachable
        3. Each slot's item is reachable by the actor → NotReachable
    """
    outfit = outfit_state.outfit
    if outfit.character_sheet.character != character.obj:
        raise PermissionDenied
    if not outfit_state.can_apply(actor=character):
        raise NotReachable

    for slot in outfit.slots.all():
        item_state = ItemState(slot.item_instance, context=character.context)
        if not item_state.is_reachable_by(character.obj):
            raise NotReachable
        # equip() handles auto-swap + multi-region atomicity inside the
        # outer transaction.
        equip(character, item_state)


@transaction.atomic
def undress(character: CharacterState) -> None:
    """Unequip every item currently worn by the character.

    Items stay in inventory (the existing unequip behavior). Idempotent on
    a naked character.
    """
    item_ids = list(
        EquippedItem.objects.filter(character=character.obj)
        .values_list("item_instance_id", flat=True)
        .distinct()
    )
    for item in ItemInstance.objects.filter(id__in=item_ids):
        item_state = ItemState(item, context=character.context)
        unequip(character, item_state)


def save_outfit(
    *,
    character_sheet: CharacterSheet,
    wardrobe: ItemInstance,
    name: str,
    description: str = "",
) -> Outfit:
    """Snapshot the character's currently-equipped items into a new Outfit.

    Validation:
        - ``wardrobe.template.is_wardrobe`` is True (raises ``NotAContainer``)
        - Reach validation (wardrobe in actor's reach) is enforced by the
          REST permission class — not duplicated here.
        - Uniqueness of (character_sheet, name) is enforced at the database
          level via UniqueConstraint; callers see ``IntegrityError`` on
          collision.

    Returns the new Outfit with its OutfitSlot rows populated.
    """
    if not wardrobe.template.is_wardrobe:
        raise NotAContainer

    with transaction.atomic():
        outfit = Outfit.objects.create(
            character_sheet=character_sheet,
            wardrobe=wardrobe,
            name=name,
            description=description,
        )
        rows = EquippedItem.objects.filter(character=character_sheet.character)
        OutfitSlot.objects.bulk_create(
            [
                OutfitSlot(
                    outfit=outfit,
                    item_instance=row.item_instance,
                    body_region=row.body_region,
                    equipment_layer=row.equipment_layer,
                )
                for row in rows
            ]
        )
    return outfit


def delete_outfit(outfit: Outfit) -> None:
    """Delete an outfit definition.

    Items are not touched — the OutfitSlot rows cascade-delete with the
    Outfit, but never the underlying ItemInstance.
    """
    outfit.delete()


@transaction.atomic
def add_outfit_slot(
    *,
    outfit: Outfit,
    item_instance: ItemInstance,
    body_region: str,
    equipment_layer: str,
) -> OutfitSlot:
    """Add or replace a slot in an outfit.

    If the same (body_region, equipment_layer) already has a slot, the old
    one is deleted first and the new one inserted.

    Validation order (raises on first failure):
        1. The item's template declares (region, layer) → ``SlotIncompatible``
        2. The item is owned by the outfit's character's account →
           ``PermissionDenied``

    The ownership check uses account-level ownership rather than current
    possession: outfits are configuration ("when applied, equip these"),
    so the question that matters is "will this character ever be able to
    apply this slot," not "are they carrying the item right now." Apply-time
    enforces reach separately, so this is the right boundary for the
    configuration layer.
    """
    template_slots = item_instance.template.cached_slots
    if not any(
        s.body_region == body_region and s.equipment_layer == equipment_layer
        for s in template_slots
    ):
        raise SlotIncompatible

    if item_instance.owner_id != outfit.character_sheet.character.db_account_id:
        raise PermissionDenied

    OutfitSlot.objects.filter(
        outfit=outfit,
        body_region=body_region,
        equipment_layer=equipment_layer,
    ).delete()
    return OutfitSlot.objects.create(
        outfit=outfit,
        item_instance=item_instance,
        body_region=body_region,
        equipment_layer=equipment_layer,
    )


@transaction.atomic
def remove_outfit_slot(
    *,
    outfit: Outfit,
    body_region: str,
    equipment_layer: str,
) -> None:
    """Remove a slot from an outfit. Idempotent — no error if not present."""
    OutfitSlot.objects.filter(
        outfit=outfit,
        body_region=body_region,
        equipment_layer=equipment_layer,
    ).delete()
