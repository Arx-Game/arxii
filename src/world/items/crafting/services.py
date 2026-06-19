"""Generic crafting orchestration — ``run_crafting_recipe`` (#1031).

This is the integration keystone of the crafting framework. It ties together the
recipe model, the kind-specific handler, the cost-staging/consumption layer, the
consequence pool, and the skill-capped quality resolver into one transactional
entry point.

The facet/style wrappers in ``world.items.services.crafting`` delegate here; this
module knows nothing about facets or styles directly — it dispatches through the
handler registry on ``CraftingRecipeKind``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db import transaction

from actions.types import WeightedConsequence
from world.checks.consequence_resolution import (
    apply_resolution,
    select_consequence_from_result,
)
from world.checks.services import perform_check
from world.checks.types import ResolutionContext
from world.items.crafting.cost import consume_cost, stage_and_assert_affordable
from world.items.crafting.models import CraftingRecipe
from world.items.crafting.quality import resolve_capped_tier
from world.items.crafting.registry import get_handler
from world.items.exceptions import CraftingNotConfigured

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB
    from evennia.objects.models import ObjectDB

    from world.items.crafting.constants import CraftingRecipeKind
    from world.items.models import ItemInstance, QualityTier
    from world.traits.models import CheckOutcome


@dataclass(frozen=True)
class CraftRunResult:
    """Generic outcome of a ``run_crafting_recipe`` attempt.

    The facet/style wrappers map this onto their domain-specific result
    dataclasses (``FacetCraftResult`` / ``StyleCraftResult``).
    """

    attached: bool
    outcome: CheckOutcome | None
    row: object | None
    quality_tier: QualityTier | None
    consumed: dict
    consequence_label: str | None


@transaction.atomic
def run_crafting_recipe(
    *,
    kind: CraftingRecipeKind,
    crafter_account: AccountDB,
    crafter_character: ObjectDB,
    item_instance: ItemInstance,
    target: object,
) -> CraftRunResult:
    """Run a crafting attempt end-to-end for ``kind`` against ``target``.

    Pipeline (all inside one transaction):

    1. Resolve the recipe for ``kind``; raise ``CraftingNotConfigured`` if it is
       missing or has no ``check_type``.
    2. Pre-validate attachability via the kind's handler — BEFORE rolling, so a
       full/duplicate item never wastes a roll.
    3. Stage and assert affordability of AP / Anima / materials. Raises
       ``CraftingCostUnaffordable`` before any roll occurs.
    4. Roll the recipe's check.
    5. Select a weighted consequence from the recipe's pool for the rolled tier.
    6. Consume cost per the selected consequence's consumption policy (or the
       recipe default when the tier has no authored consequence).
    7. Apply the consequence's effects.
    8. On sufficient success level, resolve the skill-capped quality tier and
       apply the attachment via the handler.

    Args:
        kind: Which recipe drives this attempt.
        crafter_account: The account performing the attachment (provenance).
        crafter_character: The ObjectDB whose traits roll the check + hold AP/Anima.
        item_instance: The item receiving the attachment.
        target: The Facet or Style to attach.

    Returns:
        A ``CraftRunResult`` describing the outcome.

    Raises:
        CraftingNotConfigured: No recipe for ``kind``, or it has no ``check_type``.
        CraftingCostUnaffordable: The crafter cannot afford the recipe cost.
    """
    # --- 1. Resolve the recipe ---
    try:
        recipe = CraftingRecipe.objects.get(kind=kind)
    except CraftingRecipe.DoesNotExist as exc:
        raise CraftingNotConfigured from exc
    if recipe.check_type is None:
        raise CraftingNotConfigured

    # --- 2. Pre-validate (never waste a roll) ---
    handler = get_handler(kind)
    handler.pre_validate(item_instance=item_instance, target=target)

    # --- 3. Stage + assert affordability (before rolling) ---
    staged = stage_and_assert_affordable(
        recipe=recipe,
        crafter_character=crafter_character,
        crafter_character_sheet=item_instance.holder_character_sheet,
    )

    # --- 4. Roll ---
    check_result = perform_check(crafter_character, recipe.check_type, recipe.base_difficulty)

    # --- 5. Select a weighted consequence for the rolled tier ---
    rows = list(
        recipe.consequence_rows.all().select_related("consequence", "consequence__outcome_tier")
    )
    rows_by_id = {r.consequence_id: r for r in rows}
    weighted = [
        WeightedConsequence(
            consequence=r.consequence,
            weight=(r.weight_override if r.weight_override is not None else r.consequence.weight),
            character_loss=r.consequence.character_loss,
        )
        for r in rows
    ]
    pending = select_consequence_from_result(crafter_character, check_result, weighted)
    selected = pending.selected_consequence
    row_for_selected = rows_by_id.get(selected.pk)
    consumption = (
        row_for_selected.cost_consumption
        if row_for_selected is not None
        else recipe.default_cost_consumption
    )
    consequence_label = selected.label

    # --- 6. Consume cost per the selected consumption policy ---
    consumed = consume_cost(
        crafter_character=crafter_character,
        staged=staged,
        consumption=consumption,
    )

    # --- 7. Apply the consequence's effects ---
    apply_resolution(pending, ResolutionContext(character=crafter_character))

    # --- 8. Resolve quality + apply the attachment on sufficient success ---
    if check_result.success_level >= recipe.min_success_level:
        tier = resolve_capped_tier(
            recipe=recipe,
            crafter_character=crafter_character,
            check_result=check_result,
        )
        row = handler.apply(
            crafter_account=crafter_account,
            item_instance=item_instance,
            target=target,
            quality_tier=tier,
        )
        attached = True
    else:
        tier = None
        row = None
        attached = False

    return CraftRunResult(
        attached=attached,
        outcome=check_result.outcome,
        row=row,
        quality_tier=tier,
        consumed=consumed,
        consequence_label=consequence_label,
    )
