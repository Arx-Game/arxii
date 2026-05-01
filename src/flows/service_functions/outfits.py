"""Outfit-related service functions.

The action-layer entry points (called from the action layer for IC actions
that have game-state consequences). Save / delete / slot-edit services
live alongside but are called from the REST layer for player bookkeeping.
"""

from __future__ import annotations

from django.db import transaction

from flows.object_states.character_state import CharacterState
from flows.object_states.item_state import ItemState
from flows.object_states.outfit_state import OutfitState
from flows.service_functions.inventory import equip, unequip
from world.items.exceptions import NotReachable, PermissionDenied
from world.items.models import EquippedItem, ItemInstance


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
