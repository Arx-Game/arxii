"""Service: equip and unequip items on character slots."""

from __future__ import annotations

from django.db import transaction

from world.items.exceptions import SlotConflict, SlotIncompatible
from world.items.models import EquippedItem, ItemInstance


@transaction.atomic
def equip_item(
    *,
    character_sheet,  # CharacterSheet — caller holds the sheet; .character is the ObjectDB
    item_instance: ItemInstance,
    body_region: str,
    equipment_layer: str,
) -> EquippedItem:
    """Place ``item_instance`` on ``character_sheet``'s slot.

    Args:
        character_sheet: The CharacterSheet whose character will wear the item.
            We accept CharacterSheet (not raw ObjectDB) so callers remain in the
            character-data layer and avoid passing bare ObjectDB references.
        item_instance: The item to equip.
        body_region: A BodyRegion choice value.
        equipment_layer: An EquipmentLayer choice value.

    Returns:
        The newly created EquippedItem row.

    Raises:
        SlotConflict: Another EquippedItem already occupies the slot.
        SlotIncompatible: The item template doesn't declare this slot.
    """
    char_obj = character_sheet.character
    if EquippedItem.objects.filter(
        character=char_obj,
        body_region=body_region,
        equipment_layer=equipment_layer,
    ).exists():
        raise SlotConflict
    template_slots = item_instance.template.cached_slots
    if not any(
        s.body_region == body_region and s.equipment_layer == equipment_layer
        for s in template_slots
    ):
        raise SlotIncompatible
    equipped = EquippedItem.objects.create(
        character=char_obj,
        item_instance=item_instance,
        body_region=body_region,
        equipment_layer=equipment_layer,
    )
    char_obj.equipped_items.invalidate()
    return equipped


@transaction.atomic
def unequip_item(*, equipped_item: EquippedItem) -> None:
    """Remove an EquippedItem and invalidate the character's handler cache.

    Args:
        equipped_item: The row to delete.
    """
    char_obj = equipped_item.character
    equipped_item.delete()
    char_obj.equipped_items.invalidate()
