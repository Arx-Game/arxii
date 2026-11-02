"""Working a meaningful item into a new one (#4512, #4462 section 6.4).

The crafter chooses one item they hold; the making uses it up and records it on the new
piece. The recorded points are what the source meant to the crafter at that moment (the
reader's answer, never a price), so the new piece carries them after the source is gone.
Recipe materials are allocated by template as before and record nothing, so no
meaningful item is consumed by accident.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.items.exceptions import WorkedFromUnavailable
from world.items.models import ItemLineage
from world.items.services.meaning import item_meaning
from world.items.services.usage import destroy_consumed_item_instance

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.items.models import ItemInstance


def validate_worked_from(source: ItemInstance, *, crafter: CharacterSheet) -> None:
    """The source must be a piece in play that the crafter holds, never a natural weapon."""
    if source.destroyed_at is not None or source.holder_character_sheet_id != crafter.pk:
        raise WorkedFromUnavailable
    from world.items.services.natural_weapons import require_removable  # noqa: PLC0415

    require_removable(source)


def work_in_item(
    item: ItemInstance, source: ItemInstance, *, crafter: CharacterSheet
) -> ItemLineage:
    """Record ``source`` as what ``item`` was worked from, then use ``source`` up.

    The source is soft-destroyed with its design kept (``preserve=True``), so its name,
    description and history stay on record. Caller owns the transaction.
    """
    from world.worship.invocation_services import get_devotion_config  # noqa: PLC0415

    validate_worked_from(source, crafter=crafter)
    points = item_meaning(source, crafter, config=get_devotion_config()).points
    lineage = ItemLineage.objects.create(
        item=item, source_item=source, source_name=source.display_name, points=points
    )
    del item.cached_lineage  # examine's "Worked from" reads it
    destroy_consumed_item_instance(source, preserve=True, note=f"Worked into {item.display_name}")
    return lineage
