"""Personal touchstone attunement (#707).

``attune_touchstone`` binds a resonance-tied ItemInstance to the performing
character — it does NOT consume the item; that happens later when the
target ritual (e.g. Sanctification) actually runs, via
``resolve_and_consume_ritual_components``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.utils import timezone

from world.magic.exceptions import RitualComponentError

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.items.models import ItemInstance
    from world.magic.models import Ritual


def attune_touchstone(
    *,
    character_sheet: CharacterSheet,
    ritual: Ritual | None,  # noqa: ARG001
    item_instance: ItemInstance,
    **kwargs: Any,  # noqa: ARG001
) -> ItemInstance:
    """Bind ``item_instance`` to ``character_sheet`` as a personal touchstone.

    Args:
        character_sheet: The performing character.
        ritual: The dispatching Ritual row (unused here — accepted per the
            SERVICE-dispatch convention, `character_sheet=` first, `ritual=`
            forwarded).
        item_instance: The resonance-tied item to attune.

    Returns:
        The same ``item_instance``, now attuned.

    Raises:
        RitualComponentError: If the item isn't resonance-tied, isn't held by
            the performer, is already attuned, or the performer hasn't
            claimed the item's tied Resonance.
    """
    from world.magic.models import CharacterResonance  # noqa: PLC0415

    if item_instance.template.tied_resonance_id is None:
        exc = RitualComponentError()
        exc.user_message = f"'{item_instance.template}' is not a resonance-tied item."
        raise exc
    if item_instance.holder_character_sheet_id != character_sheet.pk:
        exc = RitualComponentError()
        exc.user_message = "You must be holding the item to attune it."
        raise exc
    if item_instance.attuned_to_character_sheet_id is not None:
        exc = RitualComponentError()
        exc.user_message = "This item is already attuned."
        raise exc
    if not CharacterResonance.objects.filter(
        character_sheet=character_sheet, resonance_id=item_instance.template.tied_resonance_id
    ).exists():
        exc = RitualComponentError()
        exc.user_message = (
            f"You have not claimed the {item_instance.template.tied_resonance} Resonance."
        )
        raise exc

    item_instance.attuned_to_character_sheet = character_sheet
    item_instance.attuned_at = timezone.now()
    item_instance.save(update_fields=["attuned_to_character_sheet", "attuned_at"])
    return item_instance
