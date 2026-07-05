"""Narrative, GM-mediated item grants (#707).

No merchant/shop system exists in this codebase — touchstones and reagents
are acquired via story (adventuring loot, mission rewards, or a GM
hand-awarding a specific item at a story-earned moment), not purchase.
This is the shared grant primitive both the staff command and the Mission
ITEM reward sink call. Mirrors mint_instrument's shape
(world/currency/services.py:160-190).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from world.character_sheets.models import CharacterSheet
    from world.items.models import ItemInstance, ItemTemplate


def grant_touchstone_item_to_character(
    *,
    character_sheet: CharacterSheet,
    template: ItemTemplate,
    granted_by: AccountDB | None = None,  # noqa: ARG001
) -> ItemInstance:
    """Create an ItemInstance of ``template``, held by ``character_sheet``.

    Args:
        character_sheet: The recipient.
        template: The ItemTemplate to instantiate.
        granted_by: The staff account granting this, for audit purposes only
            — not surfaced to the recipient (per the award_kudos precedent:
            don't leak "staff gave you this" unless the GM chooses to narrate
            it themselves).

    Returns:
        The newly created ItemInstance.
    """
    from world.items.models import ItemInstance  # noqa: PLC0415

    return ItemInstance.objects.create(template=template, holder_character_sheet=character_sheet)
