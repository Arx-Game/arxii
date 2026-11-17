"""Reading the Primum a character carries, and minting Primum items (#5125)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.items.models import ItemInstance, ItemSubstance, ItemTemplate
from world.items.services.materialize import materialize_item_game_object
from world.magic.exceptions import HarvestNotConfigured

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.items.models import QualityTier
    from world.magic.models import Substance


def item_substance_rows(sheet: CharacterSheet) -> list[ItemSubstance]:
    """The substance rows of the items ``sheet`` has equipped, in one query.

    An item worn across several body regions has several equipped rows but is listed once.
    """
    return list(
        ItemSubstance.objects.filter(item_instance__equipped_slots__character=sheet)
        .select_related("substance", "step", "item_instance__template")
        .distinct()
    )


def mint_primum_items(
    sheet: CharacterSheet,
    substance: Substance,
    quantity: int,
    quality_tier: QualityTier | None,
) -> list[ItemInstance]:
    """Give ``sheet`` ``quantity`` Primum items of ``substance``, each in her inventory.

    The item is the template whose ``primum_substance`` is ``substance``. A stackable template
    mints stacks (one stack unless ``quantity`` is past its stack size); any other mints one
    item per unit. Each is materialised as a physical object she carries. Raises
    ``HarvestNotConfigured`` when no template is the Primum item of ``substance``.
    """
    template = ItemTemplate.objects.filter(primum_substance=substance).first()
    if template is None:
        raise HarvestNotConfigured
    if template.is_stackable:
        stack_size = max(template.max_stack_size, 1)
        counts = [min(stack_size, quantity - done) for done in range(0, quantity, stack_size)]
    else:
        counts = [1] * quantity
    minted: list[ItemInstance] = []
    for count in counts:
        instance = ItemInstance.objects.create(
            template=template,
            holder_character_sheet=sheet,
            quantity=count,
            quality_tier=quality_tier,
        )
        materialize_item_game_object(instance, sheet)
        minted.append(instance)
    return minted
