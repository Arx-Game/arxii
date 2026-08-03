"""Services: check-driven facet/style crafting (Spec D / #510, #1151).

``craft_attach_facet`` and ``craft_attach_style`` are thin wrappers over the
generic crafting orchestrator (``world.items.crafting.services.run_crafting_recipe``).
They keep their original signatures and map the generic ``CraftRunResult`` onto
the domain-specific ``FacetCraftResult`` / ``StyleCraftResult``.

``compute_quality_score`` lives here because ``world.items.crafting.quality``
imports it — keep it in this module.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from world.items.crafting.constants import CraftingRecipeKind
from world.items.types import FacetCraftResult, ItemCreateResult, StyleCraftResult

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB
    from evennia.objects.models import ObjectDB

    from world.checks.types import CheckResult
    from world.items.models import ItemFacet, ItemInstance, ItemStyle, ItemTemplate, Style
    from world.magic.models import Facet


def compute_quality_score(check_result: CheckResult, *, step: int, min_success_level: int) -> int:
    """Quality score = total_points + graded bonus + the roll's luck (#2886).

    The graded outcome shifts the score above the crafter's raw skill points,
    and the SAME d100 that picked the band adds a luck spread
    (``(effective_roll − offset) ÷ divisor``, ≈ −9…+11) — a deterministic
    result every craft is unsatisfying, and refinement exists precisely to
    grind away a cold roll (Apostate's ruling, 2026-08-02). ``effective_roll``
    of 0 (forced test outcomes) contributes no luck.
    """
    from world.items.crafting.constants import (  # noqa: PLC0415
        QUALITY_LUCK_DIVISOR,
        QUALITY_LUCK_OFFSET,
    )

    bonus = max(0, check_result.success_level - min_success_level) * step
    luck = (
        (check_result.effective_roll - QUALITY_LUCK_OFFSET) // QUALITY_LUCK_DIVISOR
        if check_result.effective_roll
        else 0
    )
    return check_result.total_points + bonus + luck


def craft_attach_facet(
    *,
    crafter_account: AccountDB,
    crafter_character: ObjectDB,
    item_instance: ItemInstance,
    facet: Facet,
) -> FacetCraftResult:
    """Run the facet-attach recipe and map the result onto ``FacetCraftResult``.

    Delegates to ``run_crafting_recipe`` (which pre-validates attachability and
    affordability before rolling, rolls the check, consumes cost per the selected
    consequence, and attaches the facet at the skill-capped tier on success).
    Ownership is enforced by the view permission.

    Args:
        crafter_account: The AccountDB applying the facet (stored as applied_by_account).
        crafter_character: The ObjectDB whose traits roll the Enchanting check.
        item_instance: The ItemInstance receiving the facet.
        facet: The Facet to attach.

    Returns:
        FacetCraftResult with attached=True and a resolved quality_tier on success,
        or attached=False with item_facet=None and quality_tier=None on failure.

    Raises:
        CraftingNotConfigured: No recipe/CheckType is wired, or no QualityTier rows exist.
        CraftingCostUnaffordable: The crafter cannot afford the recipe cost.
        FacetCapacityExceeded: The item is at its template's facet_capacity.
        FacetAlreadyAttached: That facet is already present on the item.
    """
    from world.items.crafting.services import run_crafting_recipe  # noqa: PLC0415

    result = run_crafting_recipe(
        kind=CraftingRecipeKind.FACET_ATTACH,
        crafter_account=crafter_account,
        crafter_character=crafter_character,
        item_instance=item_instance,
        target=facet,
    )
    return FacetCraftResult(
        attached=result.attached,
        outcome=result.outcome,
        item_facet=cast("ItemFacet | None", result.row),
        quality_tier=result.quality_tier,
        consumed=result.consumed,
        consequence_label=result.consequence_label,
    )


def craft_attach_style(
    *,
    crafter_account: AccountDB,
    crafter_character: ObjectDB,
    item_instance: ItemInstance,
    style: Style,
) -> StyleCraftResult:
    """Run the style-attach recipe and map the result onto ``StyleCraftResult``.

    Delegates to ``run_crafting_recipe`` (which pre-validates attachability and
    affordability before rolling, rolls the check, consumes cost per the selected
    consequence, and attaches the style at the skill-capped tier on success).
    Ownership is enforced by the view permission.

    Args:
        crafter_account: The AccountDB applying the style (stored as applied_by_account).
        crafter_character: The ObjectDB whose traits roll the Enchanting check.
        item_instance: The ItemInstance receiving the style.
        style: The Style to attach.

    Returns:
        StyleCraftResult with attached=True and a resolved quality_tier on success,
        or attached=False with item_style=None and quality_tier=None on failure.

    Raises:
        CraftingNotConfigured: No recipe/CheckType is wired, or no QualityTier rows exist.
        CraftingCostUnaffordable: The crafter cannot afford the recipe cost.
        StyleCapacityExceeded: The item is at its template's style_capacity.
        StyleAlreadyAttached: That style is already present on the item.
    """
    from world.items.crafting.services import run_crafting_recipe  # noqa: PLC0415

    result = run_crafting_recipe(
        kind=CraftingRecipeKind.STYLE_ATTACH,
        crafter_account=crafter_account,
        crafter_character=crafter_character,
        item_instance=item_instance,
        target=style,
    )
    return StyleCraftResult(
        attached=result.attached,
        outcome=result.outcome,
        item_style=cast("ItemStyle | None", result.row),
        quality_tier=result.quality_tier,
        consumed=result.consumed,
        consequence_label=result.consequence_label,
    )


def craft_create_item(  # noqa: PLR0913 — orchestrator passthrough (#2878 accents)
    *,
    crafter_account: AccountDB,
    crafter_character: ObjectDB,
    output_template: ItemTemplate,
    custom_name: str = "",
    custom_description: str = "",
    accent_targets: list | None = None,
) -> ItemCreateResult:
    """Run the ITEM_CREATE recipe and map the result onto ``ItemCreateResult``.

    Delegates to ``run_crafting_recipe`` (which pre-validates the template,
    gates on station + affordability, rolls the check, consumes cost per the
    selected consequence, and creates the ItemInstance on success).

    Args:
        crafter_account: The AccountDB performing the craft (provenance).
        crafter_character: The ObjectDB whose traits roll the check + hold AP/Anima.
        output_template: The ItemTemplate to create an instance of.
        custom_name: Player-authored name override (empty = use template default).
        custom_description: Player-authored description override.

    Returns:
        ItemCreateResult with created=True and item_instance set on success,
        or created=False with item_instance=None on failure.

    Raises:
        CraftingNotConfigured: No recipe/CheckType is wired for this template.
        CraftingCostUnaffordable: The crafter cannot afford the recipe cost.
        CraftingStationRequired: No station installed.
        CraftingStationBroken: Station at 0 durability.
    """
    from world.items.crafting.services import run_crafting_recipe  # noqa: PLC0415

    result = run_crafting_recipe(
        kind=CraftingRecipeKind.ITEM_CREATE,
        crafter_account=crafter_account,
        crafter_character=crafter_character,
        item_instance=None,
        target=None,
        output_overrides={
            "output_template": output_template,
            "custom_name": custom_name,
            "custom_description": custom_description,
        },
        accent_targets=accent_targets,
    )
    return ItemCreateResult(
        created=result.attached,
        outcome=result.outcome,
        item_instance=cast("ItemInstance | None", result.row),
        quality_tier=result.quality_tier,
        consumed=result.consumed,
        consequence_label=result.consequence_label,
        accents=result.accents,
    )
