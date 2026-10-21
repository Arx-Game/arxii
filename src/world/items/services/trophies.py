"""Trophies: an item won on a deed, linked to it (#4530, #4462 section 6.4).

A mission route or a stake outcome that mints a deed and grants an item in the same
resolution links the item to the deed, so the piece reads "Trophy of <deed>" on examine and
counts by the deed's legend (``item_meaning``'s trophy signal). Only a deed credited to the
item's holder links, and only a Success or better outcome reaches here: the callers decide
that. A Partial Success or worse links nothing.

This is not the crafting fame path. ``award_crafting_fame`` (``items/crafting/reward.py``)
returns early on purpose: an ordinary masterwork risks nothing, and Legend is for risk
(#3463), so it mints no deed to link. A trophy is the opposite case: its deed was already
priced by the settlement that minted it.

The granted reward items are row-only touchstones. A trophy is a thing the character keeps,
shows, wears or gives up, so linking one makes it a physical object in the holder's
inventory, as any carried piece is.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from world.items.models import ItemInstance
    from world.societies.models import LegendEntry


def link_trophy(item: ItemInstance, entries: Iterable[LegendEntry]) -> bool:
    """Link ``item`` to the deeds in ``entries`` credited to its holder. True when it linked.

    Idempotent. The item becomes a physical object in the holder's inventory when it was
    only a row. Nothing happens for an item nobody holds or a deed credited to someone else.
    """
    from world.items.services.materialize import materialize_item_game_object  # noqa: PLC0415

    sheet = item.holder_character_sheet
    if sheet is None:
        return False
    mine = [entry for entry in entries if entry.persona.character_sheet_id == sheet.pk]
    if not mine:
        return False
    item.legend_deeds.add(*mine)
    del item.cached_trophy_deeds  # examine's "Trophy of" line reads it
    if item.game_object is None and sheet.character is not None:
        materialize_item_game_object(item, sheet)
    return True
