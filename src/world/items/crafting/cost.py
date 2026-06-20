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

from world.items.crafting.constants import PARTIAL_FRACTION, CostConsumption
from world.items.exceptions import CraftingCostUnaffordable, InsufficientMaterials
from world.items.models import ItemInstance
from world.items.services.materials import consume_pks, gather_consumable_pks

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.items.crafting.models import CraftingRecipe


@dataclass
class StagedCost:
    """Snapshot of the resources committed for a crafting attempt.

    Captured at affordability-check time so that the downstream consume step
    can apply ``CostConsumption`` semantics without re-querying.

    Attributes:
        action_points: AP required by the recipe.
        anima: Anima required by the recipe.
        material_pks: Primary keys of ``ItemInstance`` rows to consume.
    """

    action_points: int
    anima: int
    material_pks: list[int] = field(default_factory=list)


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
    # Materialise available inventory for this recipe's required templates in a
    # single query to avoid N+1 on the hot path.
    requirements = list(
        recipe.material_requirements.all().select_related("item_template", "min_quality_tier")
    )
    required_template_ids = [r.item_template_id for r in requirements]
    available: list[ItemInstance] = list(
        ItemInstance.objects.filter(
            holder_character_sheet=crafter_character_sheet,
            template_id__in=required_template_ids,
        ).select_related("quality_tier")
    )

    try:
        material_pks = gather_consumable_pks(available=available, requirements=requirements)
    except InsufficientMaterials as exc:
        msg = "You do not have the required materials."
        raise CraftingCostUnaffordable(msg) from exc

    return StagedCost(
        action_points=ap_cost,
        anima=anima_cost,
        material_pks=material_pks,
    )


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
    from world.action_points.models import ActionPointPool  # noqa: PLC0415
    from world.magic.services.anima import deduct_anima  # noqa: PLC0415

    if consumption == CostConsumption.NONE:
        return {"action_points": 0, "anima": 0, "materials": 0}

    if consumption == CostConsumption.PARTIAL:
        ap_to_spend = math.ceil(staged.action_points * PARTIAL_FRACTION)
        anima_to_spend = math.ceil(staged.anima * PARTIAL_FRACTION)
    else:  # FULL
        ap_to_spend = staged.action_points
        anima_to_spend = staged.anima

    # Deduct AP
    if ap_to_spend > 0:
        pool = ActionPointPool.get_or_create_for_character(crafter_character)
        if not pool.spend(ap_to_spend):
            msg = "Action points were spent elsewhere before crafting completed."
            raise CraftingCostUnaffordable(msg)

    # Deduct Anima
    if anima_to_spend > 0:
        deduct_anima(crafter_character, anima_to_spend, lethal=False)

    # Consume materials (PARTIAL and FULL both consume ALL materials)
    materials_consumed = len(staged.material_pks)
    consume_pks(staged.material_pks)

    return {
        "action_points": ap_to_spend,
        "anima": anima_to_spend,
        "materials": materials_consumed,
    }
