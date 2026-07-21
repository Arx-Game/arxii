"""Crafting cost staging, affordability pre-check, and fractional consumption.

Provides two public functions consumed by the crafting orchestration layer (Task 7+):

* ``stage_and_assert_affordable`` — reads recipe costs, validates the crafter has
  sufficient AP, Anima, and materials, and returns a ``StagedCost`` snapshot.
* ``consume_cost`` — applies ``CostConsumption`` semantics to the snapshot,
  deducting resources according to the outcome tier.

Both functions receive the crafter as two arguments: ``crafter_character`` (the
``ObjectDB`` that holds the AP pool and Anima row) and ``crafter_character_sheet``
(the ``CharacterSheet`` that holds the inventory).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import TYPE_CHECKING

from django.db.models import Q

from world.items.crafting.constants import PARTIAL_FRACTION, CostConsumption
from world.items.exceptions import CraftingCostUnaffordable, InsufficientMaterials
from world.items.models import ItemInstance
from world.items.services.materials import consume_materials, gather_consumable_pks

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.items.crafting.models import CraftingRecipe
    from world.items.models import MaterialCategory


@dataclass
class StagedCost:
    """Snapshot of the resources committed for a crafting attempt.

    Captured at affordability-check time so that the downstream consume step
    can apply ``CostConsumption`` semantics without re-querying.

    Attributes:
        action_points: AP required by the recipe.
        anima: Anima required by the recipe.
        material_allocations: ``(ItemInstance, amount)`` tuples to consume.
        bucket_spends: ``(tier, value)`` common-gem bulk spends (Build 0b).
        crafter_character_sheet: The sheet whose common-gem buckets ``bucket_spends`` draw from.
    """

    action_points: int
    anima: int
    material_allocations: list[tuple[ItemInstance, int]] = field(default_factory=list)
    bucket_spends: list[tuple[MaterialCategory, int]] = field(default_factory=list)
    crafter_character_sheet: CharacterSheet | None = None


def stage_and_assert_affordable(
    *,
    recipe: CraftingRecipe,
    crafter_character: ObjectDB,
    crafter_character_sheet: CharacterSheet,
) -> StagedCost:
    """Assert the crafter can afford ``recipe`` and return a ``StagedCost`` snapshot.

    Checks AP, Anima, and material inventory in sequence. Raises
    ``CraftingCostUnaffordable`` on the *first* shortfall encountered so the
    caller receives a specific message.

    Material availability is validated via the shared ``gather_consumable_pks``
    helper (raises ``InsufficientMaterials``), which is caught and re-raised as
    ``CraftingCostUnaffordable`` so callers only need to handle one exception type.

    Args:
        recipe: The ``CraftingRecipe`` being attempted.
        crafter_character: The ``ObjectDB`` character (holds AP pool + Anima row).
        crafter_character_sheet: The ``CharacterSheet`` (holds inventory).

    Returns:
        ``StagedCost`` snapshot — pass this to ``consume_cost``.

    Raises:
        CraftingCostUnaffordable: When AP, Anima, or materials are insufficient.
    """
    from world.action_points.models import ActionPointPool  # noqa: PLC0415
    from world.magic.models import CharacterAnima  # noqa: PLC0415

    # --- AP check ---
    ap_cost = recipe.action_point_cost
    if ap_cost > 0:
        pool = ActionPointPool.get_or_create_for_character(crafter_character)
        if pool.current < ap_cost:
            msg = f"You need {ap_cost} action points but only have {pool.current}."
            raise CraftingCostUnaffordable(msg)

    # --- Anima check ---
    anima_cost = recipe.anima_cost
    if anima_cost > 0:
        anima_row = CharacterAnima.objects.filter(character=crafter_character).first()
        current_anima = anima_row.current if anima_row is not None else 0
        if current_anima < anima_cost:
            msg = f"You need {anima_cost} anima but only have {current_anima}."
            raise CraftingCostUnaffordable(msg)

    # --- Material check ---
    requirements = list(
        recipe.material_requirements.all().select_related(
            "item_template", "min_quality_tier", "material_category"
        )
    )
    # Split bulk value-requirements (Build 0b — spent from the crafter's common-gem
    # buckets) from instance-requirements (0a — counted/consumed from inventory).
    value_reqs = [r for r in requirements if r.required_value is not None]
    instance_reqs = [r for r in requirements if r.required_value is None]

    # Instance requirements: materialise available inventory in one query (avoid N+1).
    required_template_ids = [r.item_template_id for r in instance_reqs if r.item_template_id]
    required_category_ids = [
        r.material_category_id for r in instance_reqs if r.material_category_id
    ]
    available: list[ItemInstance] = list(
        ItemInstance.objects.filter(holder_character_sheet=crafter_character_sheet)
        .filter(
            Q(template_id__in=required_template_ids)
            | Q(template__material_category_id__in=required_category_ids)
        )
        .select_related("quality_tier", "template")
    )
    try:
        material_allocations = gather_consumable_pks(
            available=available, requirements=instance_reqs
        )
    except InsufficientMaterials as exc:
        msg = "You do not have the required materials."
        raise CraftingCostUnaffordable(msg) from exc

    # Bulk value requirements: aggregate per tier and assert the buckets can cover them.
    bucket_spends = _stage_bucket_spends(value_reqs, crafter_character_sheet)

    return StagedCost(
        action_points=ap_cost,
        anima=anima_cost,
        material_allocations=material_allocations,
        bucket_spends=bucket_spends,
        crafter_character_sheet=crafter_character_sheet,
    )


def _stage_bucket_spends(
    value_reqs: list, crafter_character_sheet: CharacterSheet
) -> list[tuple[MaterialCategory, int]]:
    """Aggregate common-gem value requirements per tier and assert affordability.

    Returns ``(tier, value)`` spends to apply at consume time. Raises
    ``CraftingCostUnaffordable`` if any tier's bucket holds less than required.
    """
    from world.items.gems.buckets import common_gem_value  # noqa: PLC0415

    needed: dict[int, tuple[MaterialCategory, int]] = {}
    for req in value_reqs:
        tier = req.material_category
        _, running = needed.get(tier.pk, (tier, 0))
        needed[tier.pk] = (tier, running + req.required_value)

    spends: list[tuple[MaterialCategory, int]] = []
    for tier, value in needed.values():
        if common_gem_value(crafter_character_sheet, tier) < value:
            msg = "You do not have enough common gems for this."
            raise CraftingCostUnaffordable(msg)
        spends.append((tier, value))
    return spends


def consume_cost(
    *,
    crafter_character: ObjectDB,
    staged: StagedCost,
    consumption: CostConsumption,
) -> dict[str, int]:
    """Apply ``consumption`` semantics to a ``StagedCost`` snapshot.

    Semantics (authoritative per ``CostConsumption`` TextChoices):
    * ``NONE``    — consume nothing; AP, Anima, and materials are untouched.
    * ``PARTIAL`` — consume ``ceil(cost * PARTIAL_FRACTION)`` of AP and Anima;
                    consume ALL materials in full.
    * ``FULL``    — consume AP, Anima, and all materials in full.

    Args:
        crafter_character: The ``ObjectDB`` character (AP pool + Anima row).
        staged: The ``StagedCost`` snapshot from ``stage_and_assert_affordable``.
        consumption: ``CostConsumption`` value controlling how much is deducted.

    Returns:
        Summary dict of what was actually consumed:
        ``{"action_points": n, "anima": n, "materials": k}``.
    """

    if consumption == CostConsumption.NONE:
        return {"action_points": 0, "anima": 0, "materials": 0, "common_gem_value": 0}

    if consumption == CostConsumption.PARTIAL:
        ap_to_spend = math.ceil(staged.action_points * PARTIAL_FRACTION)
        anima_to_spend = math.ceil(staged.anima * PARTIAL_FRACTION)
    else:  # FULL
        ap_to_spend = staged.action_points
        anima_to_spend = staged.anima

    _deduct_action_points(crafter_character, ap_to_spend)
    _deduct_anima(crafter_character, anima_to_spend)

    # Consume materials (PARTIAL and FULL both consume ALL materials)
    materials_consumed = len(staged.material_allocations)
    consume_materials(staged.material_allocations)

    # Spend common-gem bulk value (PARTIAL and FULL both spend it in full, like materials).
    bucket_value_spent = _spend_common_gem_buckets(staged)

    return {
        "action_points": ap_to_spend,
        "anima": anima_to_spend,
        "materials": materials_consumed,
        "common_gem_value": bucket_value_spent,
    }


def _deduct_action_points(crafter_character: ObjectDB, ap_to_spend: int) -> None:
    """Deduct action points, raising if a concurrent spend left the pool short."""
    if ap_to_spend <= 0:
        return
    from world.action_points.models import ActionPointPool  # noqa: PLC0415

    pool = ActionPointPool.get_or_create_for_character(crafter_character)
    if not pool.spend(ap_to_spend):
        msg = "Action points were spent elsewhere before crafting completed."
        raise CraftingCostUnaffordable(msg)


def _deduct_anima(crafter_character: ObjectDB, anima_to_spend: int) -> None:
    """Deduct anima, asserting sufficiency first so the summary is truthful.

    ``deduct_anima(lethal=False)`` *clamps* to available anima and never draws life
    force, so a concurrent spend that dropped the balance below ``anima_to_spend``
    (between staging and now) would be silently absorbed and the consumed-summary
    would over-report. Assert sufficiency first and fail-hard like AP does, so the
    returned ``anima`` is always truthful.
    """
    if anima_to_spend <= 0:
        return
    from world.magic.models import CharacterAnima  # noqa: PLC0415
    from world.magic.services.anima import deduct_anima  # noqa: PLC0415

    anima_row = CharacterAnima.objects.filter(character=crafter_character).first()
    current_anima = anima_row.current if anima_row is not None else 0
    if current_anima < anima_to_spend:
        msg = "Anima was spent elsewhere before crafting completed."
        raise CraftingCostUnaffordable(msg)
    deduct_anima(crafter_character, anima_to_spend, lethal=False)


def _spend_common_gem_buckets(staged: StagedCost) -> int:
    """Spend common-gem bulk value for each tier in ``staged.bucket_spends``.

    Returns the total gem value spent. Raises ``CraftingCostUnaffordable`` if a
    concurrent spend left a tier short.
    """
    sheet = staged.crafter_character_sheet
    if not staged.bucket_spends or sheet is None:
        return 0
    from world.items.exceptions import InsufficientCommonGems  # noqa: PLC0415
    from world.items.gems.buckets import spend_common_gems  # noqa: PLC0415

    bucket_value_spent = 0
    for tier, value in staged.bucket_spends:
        try:
            spend_common_gems(sheet, tier, value)
        except InsufficientCommonGems as exc:
            msg = "Common gems were spent elsewhere before crafting completed."
            raise CraftingCostUnaffordable(msg) from exc
        bucket_value_spent += value
    return bucket_value_spent
