"""Dedicating a piece to one other character (#4512, #4462 section 6.4).

A dedication is written once, by the maker at making or by the commissioner on a
commission, and is permanent: an item has at most one. There is no self-dedication; a
commission for yourself already counts through your design and the artist's tie. Giving
the piece to the dedicatee is the ordinary ``give``; the dedication does not move it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.utils import timezone

from world.items.exceptions import CannotDedicateToSelf, ItemAlreadyDedicated

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.items.models import ItemInstance
    from world.scenes.models import Persona


def validate_dedication(
    item: ItemInstance | None, *, by_sheet: CharacterSheet, to: Persona
) -> None:
    """Refuse a dedication that cannot be written. ``item`` is None before the piece exists
    (a making that has not rolled yet)."""
    if to.character_sheet_id == by_sheet.pk:
        raise CannotDedicateToSelf
    if item is not None and item.dedicated_at is not None:
        raise ItemAlreadyDedicated


def dedicate_item(item: ItemInstance, *, by: Persona, to: Persona) -> None:
    """Write the dedication on ``item``: made for ``to`` by ``by``. Caller owns the
    transaction. Saves with ``update_fields`` (ADR-0008)."""
    validate_dedication(item, by_sheet=by.character_sheet, to=to)
    item.dedicated_by_persona = by
    item.dedicated_to_persona = to
    item.dedicated_at = timezone.now()
    item.save(update_fields=["dedicated_by_persona", "dedicated_to_persona", "dedicated_at"])
