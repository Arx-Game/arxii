"""Worn conditions: the conditions a character's worn items put on her (#5074).

``ItemWornCondition`` rows say which condition an item gives its wearer. This module
keeps her conditions in step with what she wears, the way
``world.species.services.reconcile_sunlight_exposure`` keeps sunlight exposure in step
with her surroundings. Each condition gear gives records the item that gave it
(``ConditionInstance.source_item``), so the reconcile touches only conditions gear owns:
one a technique or any other source put on her is never removed or repointed here.

The item's name is never copied onto the condition: the wearer's condition list reads it
from ``source_item`` (``ConditionInstanceSerializer``), so a rename shows at once.

A condition gear gave and that was then dispelled, or lapsed through upkeep, leaves no
instance behind. Nothing here brings it back unless the caller names the row that should
apply it (she put the item on, her attunement reached its level, staff saved the row), so
the condition stays off until she takes the item off and puts it back on.
"""

from __future__ import annotations

from collections.abc import Iterable

from world.character_sheets.models import CharacterSheet
from world.conditions.models import ConditionInstance, ConditionTemplate
from world.conditions.services import apply_condition, has_condition, remove_condition
from world.items.models import EquippedItem, ItemInstance, ItemWornCondition


def worn_item_ids(character_sheet: CharacterSheet) -> list[int]:
    """Each item she wears once, however many slots it fills, in the order it went on."""
    ids = EquippedItem.objects.filter(character=character_sheet).order_by("pk")
    seen: dict[int, None] = {}
    for item_id in ids.values_list("item_instance_id", flat=True):
        seen.setdefault(item_id, None)
    return list(seen)


def _attunement_by_item(character_sheet: CharacterSheet, item_ids: list[int]) -> dict[int, int]:
    """Her attunement level to each worn mantle: item pk to the mantle level her thread holds.

    A thread's stored level runs ten to one with a mantle's levels (its cap is the highest
    cleared level times ten), so the mantle level it has reached is ``thread_rung``. A
    retired thread attunes to nothing.
    """
    from world.magic.constants import TargetKind  # noqa: PLC0415
    from world.magic.models import Thread  # noqa: PLC0415
    from world.magic.services.threads import thread_rung  # noqa: PLC0415

    rows = Thread.objects.filter(
        owner=character_sheet,
        target_kind=TargetKind.MANTLE,
        retired_at__isnull=True,
        target_mantle__item_instance_id__in=item_ids,
    ).values_list("target_mantle__item_instance_id", "level")
    return {item_id: thread_rung(level) for item_id, level in rows}


def _granting_items(
    character_sheet: CharacterSheet,
) -> tuple[dict[int, list[ItemInstance]], dict[int, ItemWornCondition]]:
    """What her worn items give her now.

    Returns the items that give each condition template (in the order they went on, so the
    first is the one that wins a tie) and one eligible row per template. A row with a
    mantle level counts only once her attunement to that mantle has reached it.
    """
    item_ids = worn_item_ids(character_sheet)
    if not item_ids:
        return {}, {}
    order = {item_id: index for index, item_id in enumerate(item_ids)}
    rows = sorted(
        ItemWornCondition.objects.filter(item_instance_id__in=item_ids).select_related(
            "condition", "item_instance", "item_instance__template"
        ),
        key=lambda row: (order[row.item_instance_id], row.pk),
    )
    attunement = (
        _attunement_by_item(character_sheet, item_ids)
        if any(row.mantle_level is not None for row in rows)
        else {}
    )
    items_by_template: dict[int, list[ItemInstance]] = {}
    row_by_template: dict[int, ItemWornCondition] = {}
    for row in rows:
        if row.mantle_level is not None and attunement.get(row.item_instance_id, 0) < (
            row.mantle_level
        ):
            continue
        items_by_template.setdefault(row.condition_id, []).append(row.item_instance)
        row_by_template.setdefault(row.condition_id, row)
    return items_by_template, row_by_template


def reconcile_worn_conditions(
    character_sheet: CharacterSheet,
    *,
    apply_rows: Iterable[ItemWornCondition] = (),
) -> None:
    """Bring the conditions her worn items give in step with what she wears and has reached.

    Removes a gear condition no worn item gives her any more (the item came off, or her
    attunement fell below its level). Repoints one whose item came off while another worn
    item still gives it. Applies a condition a worn item gives her, only for a row the
    caller names in ``apply_rows`` (she just put the item on, her attunement just reached
    the row's level, staff just saved the row) and only when she does not already hold the
    condition from any source. ``apply_rows`` is empty by default, so an unrelated equip,
    unequip or level raise never brings back a condition that was dispelled.

    Runs inside the caller's transaction with no broad catch: a gear condition that fails
    to apply is a real error and the equip fails with it. A condition a trigger cancels or
    a resist roll turns away is a result, not an error, and she simply does not get it.
    """
    character = character_sheet.character
    items_by_template, row_by_template = _granting_items(character_sheet)
    owned = list(
        ConditionInstance.objects.filter(
            target=character, source_item__isnull=False, resolved_at__isnull=True
        ).select_related("condition", "source_item")
    )
    for instance in owned:
        granting = items_by_template.get(instance.condition_id)
        if not granting:
            remove_condition(character, instance.condition, include_suppressed=True)
        elif instance.source_item_id not in {item.pk for item in granting}:
            instance.source_item = granting[0]
            instance.save(update_fields=["source_item"])
    for row in apply_rows:
        granting = items_by_template.get(row.condition_id)
        if not granting:
            continue
        template: ConditionTemplate = row_by_template[row.condition_id].condition
        if has_condition(character, template, include_suppressed=True):
            continue
        apply_condition(character, template, source_item=granting[0])


def reconcile_item_wearers(
    item_instance: ItemInstance, *, apply_rows: Iterable[ItemWornCondition] = ()
) -> None:
    """Staff changed the item's worn-condition rows: reconcile whoever wears it now.

    A saved row's condition goes to the wearer (``apply_rows``); a deleted row only removes.
    """
    rows = list(apply_rows)
    sheets = CharacterSheet.objects.filter(equipped_items__item_instance=item_instance).distinct()
    for sheet in sheets:
        reconcile_worn_conditions(sheet, apply_rows=rows)


def release_worn_conditions(item_instance: ItemInstance) -> None:
    """Take off whoever holds a condition this item gave, before the item is deleted (#5074).

    A hard delete or a staff delete cascades the item's equipped rows without going through
    ``unequip_item``; ``source_item`` would then be set null and the condition, permanent
    and no longer tied to anything, could never be removed. Called by every delete path.
    """
    for instance in ConditionInstance.objects.filter(source_item=item_instance).select_related(
        "condition", "target"
    ):
        remove_condition(instance.target, instance.condition, include_suppressed=True)
