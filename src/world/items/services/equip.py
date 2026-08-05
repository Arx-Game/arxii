"""Service: equip and unequip items on character slots."""

from __future__ import annotations

import logging

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction

from world.items.exceptions import ItemPlacedNotEquippable, SlotConflict, SlotIncompatible
from world.items.models import EquippedItem, ItemInstance

logger = logging.getLogger(__name__)


@transaction.atomic
def equip_item(
    *,
    character_sheet: object,  # CharacterSheet; .character is the ObjectDB.
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
        ItemPlacedNotEquippable: ``item_instance`` is currently placed in
            a room as decor (#676 place-XOR-equip invariant).
    """
    from world.items.polish_services import can_equip_item  # noqa: PLC0415

    # #676: serialize against concurrent place_item_in_room — lock the
    # ItemInstance row, then re-check the XOR gate under the lock.
    ItemInstance.objects.select_for_update().get(pk=item_instance.pk)
    if not can_equip_item(item_instance):
        raise ItemPlacedNotEquippable
    char_obj = character_sheet.character
    if EquippedItem.objects.filter(
        character=character_sheet,
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
        character=character_sheet,
        item_instance=item_instance,
        body_region=body_region,
        equipment_layer=equipment_layer,
    )
    char_obj.equipped_items.invalidate()
    _recompute_body_persona_items_prestige(character_sheet)
    _reconcile_sun_exposure(char_obj)
    _reconceal_markings(character_sheet, item_instance, body_region)
    return equipped


@transaction.atomic
def unequip_item(*, equipped_item: EquippedItem) -> None:
    """Remove an EquippedItem and invalidate the character's handler cache.

    Args:
        equipped_item: The row to delete.
    """
    sheet = equipped_item.character
    equipped_item.delete()
    sheet.character.equipped_items.invalidate()
    _recompute_body_persona_items_prestige(sheet)
    _reconcile_sun_exposure(sheet.character)


def _reconceal_markings(
    character_sheet: object, item_instance: ItemInstance, body_region: str
) -> None:
    """Covering skin re-conceals it (#2985): a non-revealing garment landing on a
    region clears any revealed marking there — the reveal state's natural end,
    mirroring how ``EquippedItem.revealed_at`` dies with its row."""
    from typing import cast  # noqa: PLC0415

    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415
    from world.forms.services.markings import clear_revealed_markings  # noqa: PLC0415

    if item_instance.template.is_revealing:
        return
    clear_revealed_markings(cast(CharacterSheet, character_sheet), {body_region})


def _reconcile_sun_exposure(char_obj: object) -> None:
    """Wardrobe changed: re-reconcile sunlight exposure so mitigation feels responsive
    (#2846). Cheap no-op for characters without a sun-sensitivity distinction; a
    failure inside never breaks the equip transaction (isolated in the shared
    safe wrapper)."""
    from world.species.services import reconcile_sun_exposure_safely  # noqa: PLC0415

    if char_obj is None:
        return
    reconcile_sun_exposure_safely(char_obj)


def _recompute_body_persona_items_prestige(character_sheet: object) -> None:
    """Re-credit ``prestige_from_items`` on the body's PRIMARY persona.

    #676 Phase F: fashion polish is body-keyed and the currently-presented
    persona is credited. We don't have a "presented persona" service yet,
    so we recompute for PRIMARY (the most common presented identity).
    When the persona-switch flow lands, that service will call
    ``recompute_persona_prestige_from_items`` for the newly-presented
    persona using the same helper.
    """
    from world.items.polish_services import recompute_persona_prestige_from_items  # noqa: PLC0415

    try:
        persona = character_sheet.primary_persona
    except ObjectDoesNotExist:
        # Sheet invariant violated (no PRIMARY persona): no prestige credit,
        # but log it — this is a broken invariant, not an expected state.
        logger.exception("primary_persona missing for sheet %s", character_sheet.pk)
        return
    if persona is not None:
        recompute_persona_prestige_from_items(persona)
