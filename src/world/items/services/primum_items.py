"""Reading the Primum a character carries (#5125)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.items.models import ItemSubstance

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet


def item_substance_rows(sheet: CharacterSheet) -> list[ItemSubstance]:
    """The substance rows of the items ``sheet`` has equipped, in one query.

    An item worn across several body regions has several equipped rows but is listed once.
    """
    return list(
        ItemSubstance.objects.filter(item_instance__equipped_slots__character=sheet)
        .select_related("substance", "step", "item_instance__template")
        .distinct()
    )
