"""Natural weapons: claws, a bite or horns a gift gives its holder (#4898, slice 4 of #4844).

A gift names an Unarmed item template (``Gift.natural_weapon_template``). Gaining the gift
makes one instance of it, held by the character and equipped at every slot its template
declares (staff author those at the skin layer), and the character Strikes with it on the
Unarmed strike skill like any other Unarmed weapon.

Nothing on the item marks it. An item is a natural weapon when its template is some gift's
natural weapon template and its holder holds that gift (``is_natural_weapon``). That one
predicate is the gate every removal path checks: unequip, drop, give, steal, a trade stake,
consuming it and any change of holder all refuse it.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db import transaction

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.items.models import ItemInstance
    from world.magic.models import Gift

logger = logging.getLogger(__name__)


def is_natural_weapon(item: ItemInstance) -> bool:
    """Whether ``item`` is its holder's natural weapon, and so can never be removed.

    True when the item's holder holds a gift whose natural weapon template is the item's
    template. An item nobody holds is never a natural weapon.
    """
    if item.holder_character_sheet_id is None:
        return False
    from world.magic.models import CharacterGift  # noqa: PLC0415

    return CharacterGift.objects.filter(
        character_id=item.holder_character_sheet_id,
        gift__natural_weapon_template_id=item.template_id,
    ).exists()


@transaction.atomic
def provision_natural_weapon(sheet: CharacterSheet, gift: Gift) -> ItemInstance | None:
    """Make and equip ``gift``'s natural weapon on ``sheet``, once. Idempotent.

    Returns None when the gift names no natural weapon or its template is retired. When the
    character already holds an in-play instance of the template, that one is kept (a gift
    gained twice, or two gifts naming the same claws, never makes a second) and only its
    missing slots are filled. Otherwise a new instance is made, placed on the character
    (which needs no room, so a GM character with no location gets one too) and equipped.
    """
    template = gift.natural_weapon_template
    if template is None or not template.is_active:
        return None
    from world.items.models import ItemInstance  # noqa: PLC0415
    from world.items.services.materialize import materialize_item_game_object  # noqa: PLC0415

    instance = (
        ItemInstance.objects.in_play()
        .filter(template=template, holder_character_sheet=sheet)
        .order_by("pk")
        .first()
    )
    if instance is None:
        instance = ItemInstance.objects.create(template=template, holder_character_sheet=sheet)
        materialize_item_game_object(instance, sheet)
    _equip_at_every_slot(sheet, instance)
    return instance


def _equip_at_every_slot(sheet: CharacterSheet, instance: ItemInstance) -> None:
    """Equip ``instance`` at each of its template's slots that it does not already fill.

    A slot another item already fills is left to that item and logged: the Required
    content dashboard lists a natural weapon template authored off the skin layer, which
    is the only way one can collide with worn gear.
    """
    from world.items.models import EquippedItem  # noqa: PLC0415
    from world.items.services.equip import equip_item  # noqa: PLC0415

    occupied = {
        (row.body_region, row.equipment_layer): row.item_instance_id
        for row in EquippedItem.objects.filter(character=sheet)
    }
    for slot in instance.template.cached_slots:
        key = (slot.body_region, slot.equipment_layer)
        holder_id = occupied.get(key)
        if holder_id == instance.pk:
            continue
        if holder_id is not None:
            logger.warning(
                "Natural weapon %s not equipped at %s/%s on sheet %s: slot already filled.",
                instance.pk,
                slot.body_region,
                slot.equipment_layer,
                sheet.pk,
            )
            continue
        equip_item(
            character_sheet=sheet,
            item_instance=instance,
            body_region=slot.body_region,
            equipment_layer=slot.equipment_layer,
        )
