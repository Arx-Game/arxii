"""Who holds an item now, since when, and how they came by it (#4500).

``ItemInstance.holder_character_sheet`` says who. ``held_since`` and ``holding_event``
say when and how, and they are what the carry gate and the gift and heirloom meaning
signals read (``items/services/meaning.py``). They are fields rather than ledger rows
because a GIVEN, STOLEN, TRANSFERRED, INHERITED or RECOVERED row spares an item from the
time-based purge, and writing a row on every pickup would keep worthless items from ever
being cleaned up.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.utils import timezone

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.items.models import ItemInstance, OwnershipEvent


def set_item_holder(
    item: ItemInstance, sheet: CharacterSheet | None, *, event: OwnershipEvent | None = None
) -> None:
    """Hand ``item`` to ``sheet``: the holder, the date it started and the event behind it.

    Use this for every change of an existing item to a new holder (``sheet`` None clears the
    holder, as a sheet-less taker leaves it); a freshly created item
    gets ``held_since`` from its default. ``event`` is the ledger row that moved it (a
    gift, an inheritance), when one is written; it is None for a move that writes none.
    Saves with ``update_fields`` (ADR-0008); the caller owns the transaction and writes
    ``event`` BEFORE calling so the pointer can be set.
    """
    item.holder_character_sheet = sheet
    item.held_since = timezone.now()
    item.holding_event = event
    item.save(update_fields=["holder_character_sheet", "held_since", "holding_event"])
