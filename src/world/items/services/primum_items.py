"""Reading the Primum a character carries, minting Primum items, and stamping crafts (#5125)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.items.constants import ARMOR_ARCHETYPES, BodyRegion, GearArchetype
from world.items.crafting.constants import CostConsumption
from world.items.models import EquippedItem, ItemInstance, ItemSubstance, ItemTemplate
from world.items.services.materialize import materialize_item_game_object
from world.magic.exceptions import HarvestNotConfigured

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.items.crafting.cost import StagedCost
    from world.items.models import QualityTier
    from world.magic.models import PrimumStep, Substance


def item_substance_rows(sheet: CharacterSheet) -> list[ItemSubstance]:
    """The substance rows of the items ``sheet`` has equipped, in one query.

    An item worn across several body regions has several equipped rows but is listed once.
    """
    return list(
        ItemSubstance.objects.filter(item_instance__equipped_slots__character=sheet)
        .select_related("substance", "step", "item_instance__template")
        .distinct()
    )


_HAND_REGIONS = (BodyRegion.LEFT_HAND, BodyRegion.RIGHT_HAND)
#: Gear that sits on a hand without being held in it: gloves, gauntlets, rings.
_WORN_ON_HAND = ARMOR_ARCHETYPES | {GearArchetype.CLOTHING, GearArchetype.JEWELRY}


def held_item_ids(sheet: CharacterSheet) -> set[int]:
    """The ids of the items ``sheet`` holds in a hand: a hand slot, and not gear worn there."""
    return set(
        EquippedItem.objects.filter(character=sheet, body_region__in=_HAND_REGIONS)
        .exclude(item_instance__template__gear_archetype__in=_WORN_ON_HAND)
        .values_list("item_instance_id", flat=True)
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


def stamp_primum_substances(
    *, target_item: ItemInstance, staged: StagedCost, consumption: CostConsumption
) -> list[ItemSubstance]:
    """Make ``target_item`` carry the substance of each Primum item a craft used up.

    For every staged material that is a Primum item (its template names a substance), the
    item carries that substance at the best step among the Primum used: the highest step whose
    ``item_quality`` is the quality of a Primum item used. A Primum item with no quality, or a
    quality no step is tied to, counts as the lowest step. An item that already carries the
    substance keeps the higher of the two steps. Nothing is stamped when the craft consumed
    nothing (``CostConsumption.NONE``) or when no Primum steps are authored.
    """
    from world.magic.models import PrimumStep  # noqa: PLC0415

    if consumption == CostConsumption.NONE:
        return []
    primum_used = [
        inst for inst, _amount in staged.material_allocations if inst.template.primum_substance_id
    ]
    if not primum_used:
        return []
    steps = list(PrimumStep.objects.all())  # lowest rank first (Meta.ordering)
    if not steps:
        return []
    by_quality = {step.item_quality_id: step for step in steps if step.item_quality_id}
    best: dict[int, PrimumStep] = {}
    for inst in primum_used:
        step = by_quality.get(inst.quality_tier_id, steps[0])
        held = best.get(inst.template.primum_substance_id)
        if held is None or held.rank < step.rank:
            best[inst.template.primum_substance_id] = step
    stamped = [_stamp_one(target_item, substance_id, step) for substance_id, step in best.items()]
    for equipped in EquippedItem.objects.filter(item_instance=target_item):
        # EquippedItem.character is a CharacterSheet; the handler is on its Character.
        equipped.character.character.equipped_items.invalidate()
    return stamped


def _stamp_one(target_item: ItemInstance, substance_id: int, step: PrimumStep) -> ItemSubstance:
    """Write one carried-substance row, never lowering a step the item already carries."""
    row = ItemSubstance.objects.filter(item_instance=target_item, substance_id=substance_id).first()
    if row is None:
        return ItemSubstance.objects.create(
            item_instance=target_item, substance_id=substance_id, step=step
        )
    if row.step.rank < step.rank:
        row.step = step
        row.save(update_fields=["step"])
    return row
