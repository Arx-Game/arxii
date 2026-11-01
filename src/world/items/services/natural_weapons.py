"""Natural weapons: claws, a bite or horns a gift gives its holder (#4898, slice 4 of #4844).

A gift names an Unarmed item template (``Gift.natural_weapon_template``). Gaining the gift
makes one instance of it, held by the character and equipped at every slot its template
declares (staff author those at the skin layer), and the character Strikes with it on the
Unarmed strike skill like any other Unarmed weapon.

The made item carries ``natural_weapon_gift``, the marker ``is_natural_weapon`` reads with no
query. That one predicate is the gate every removal path checks: unequip, drop, give, steal,
a trade stake, consuming it and any change of holder all refuse it. Losing the gift removes
it (``deprovision_natural_weapon``), the one path allowed around that gate.
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
    """Whether ``item`` is a natural weapon, and so can never be removed. No query.

    True when the item carries the marker ``provision_natural_weapon`` writes
    (``natural_weapon_gift``). Another copy of the same template is ordinary gear.
    """
    return item.natural_weapon_gift_id is not None


def require_removable(item: ItemInstance) -> None:
    """Raise ``NaturalWeaponNotRemovable`` when ``item`` is a natural weapon.

    The front-door check every path that takes an item off its holder runs before it
    changes anything, so the player sees the plain refusal.
    """
    if is_natural_weapon(item):
        from world.items.exceptions import NaturalWeaponNotRemovable  # noqa: PLC0415

        raise NaturalWeaponNotRemovable


@transaction.atomic
def provision_natural_weapon(sheet: CharacterSheet, gift: Gift) -> ItemInstance | None:
    """Make and equip ``gift``'s natural weapon on ``sheet``, once. Idempotent.

    Returns None when the gift names no natural weapon or its template is retired. When the
    character already holds this gift's natural weapon, that one is kept and only its
    missing slots are filled. Otherwise a new instance is made with the marker
    (``natural_weapon_gift``), placed on the character (which needs no room, so a GM
    character with no location gets one too) and equipped. An ordinary copy of the
    template the character owns is never adopted: it stays gear they may drop or give.
    """
    template = gift.natural_weapon_template
    if template is None or not template.is_active:
        return None
    from world.items.models import ItemInstance  # noqa: PLC0415
    from world.items.services.materialize import materialize_item_game_object  # noqa: PLC0415

    instance = (
        ItemInstance.objects.in_play()
        .filter(natural_weapon_gift=gift, holder_character_sheet=sheet)
        .order_by("pk")
        .first()
    )
    if instance is None:
        instance = ItemInstance.objects.create(
            template=template, holder_character_sheet=sheet, natural_weapon_gift=gift
        )
        materialize_item_game_object(instance, sheet)
    _equip_at_every_slot(sheet, instance)
    return instance


@transaction.atomic
def deprovision_natural_weapon(sheet: CharacterSheet, gift: Gift) -> int:
    """Take away ``gift``'s natural weapon from ``sheet`` when they lose the gift. Returns
    how many were removed.

    The one path that removes a natural weapon, so it deliberately goes around the removal
    gate: it clears the marker first, then hands the item to the canonical destroy helper
    (``destroy_consumed_item_instance``), which unequips it and removes its game object
    with it. Call it before the ``CharacterGift`` row goes. A character who never got the
    weapon, or a gift with none, is a no-op.
    """
    from world.items.models import ItemInstance  # noqa: PLC0415
    from world.items.services.usage import destroy_consumed_item_instance  # noqa: PLC0415

    removed = 0
    for item in ItemInstance.objects.in_play().filter(
        natural_weapon_gift=gift, holder_character_sheet=sheet
    ):
        item.natural_weapon_gift = None
        item.save(update_fields=["natural_weapon_gift"])
        destroy_consumed_item_instance(item, note=f"Lost with the gift {gift.name}.")
        removed += 1
    return removed


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
