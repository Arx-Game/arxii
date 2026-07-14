"""Stolen-provenance reads over the OwnershipEvent ledger (#1985).

The live ``holder_character_sheet`` pointer moves on steal (ADR-0091 / #1025 —
ownership genuinely transfers, with a STOLEN ledger row); what makes theft
survivable is that the ledger chain is permanent. These helpers answer "is this
item hot, and who was wronged" from that chain.

Rule (documented PLACEHOLDER, spec #1985): an item is HOT when its latest
STOLEN event has a victim (``from_character_sheet``) who never re-appears as a
recipient (``to_character_sheet``) in any LATER hands-changing event — i.e. the
wronged party never got it back. A later legitimate return (give/transfer/
inherit back to the victim) resolves the theft.
"""

from world.character_sheets.models import CharacterSheet
from world.items.constants import PROVENANCE_EVENT_TYPES, OwnershipEventType
from world.items.models import ItemInstance, OwnershipEvent


def _latest_unresolved_theft(item_instance: ItemInstance) -> OwnershipEvent | None:
    """The most recent STOLEN event whose victim never got the item back."""
    latest_theft = (
        OwnershipEvent.objects.filter(
            item_instance=item_instance,
            event_type=OwnershipEventType.STOLEN,
            from_character_sheet__isnull=False,
        )
        .order_by("-id")
        .first()
    )
    if latest_theft is None:
        return None
    returned = OwnershipEvent.objects.filter(
        item_instance=item_instance,
        id__gt=latest_theft.id,
        event_type__in=PROVENANCE_EVENT_TYPES,
        to_character_sheet=latest_theft.from_character_sheet,
    ).exists()
    return None if returned else latest_theft


def has_unresolved_stolen_provenance(item_instance: ItemInstance) -> bool:
    """True when the item is hot — stolen and never returned to the victim."""
    return _latest_unresolved_theft(item_instance) is not None


def stolen_victim(item_instance: ItemInstance) -> CharacterSheet | None:
    """The wronged party of the item's unresolved theft, or None when clean."""
    theft = _latest_unresolved_theft(item_instance)
    return theft.from_character_sheet if theft is not None else None
