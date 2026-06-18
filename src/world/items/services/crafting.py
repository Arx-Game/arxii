"""Services: check-driven facet crafting (Spec D PR2 / #510)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from world.checks.services import perform_check
from world.items.exceptions import CraftingNotConfigured
from world.items.models import FacetCraftingConfig, QualityTier
from world.items.services.facets import assert_facet_attachable, attach_facet_to_item
from world.items.services.styles import assert_style_attachable, attach_style_to_item
from world.items.types import FacetCraftResult, StyleCraftResult

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB
    from evennia.objects.models import ObjectDB

    from world.checks.types import CheckResult
    from world.items.models import ItemInstance, Style
    from world.magic.models import Facet


def get_facet_crafting_config() -> FacetCraftingConfig:
    """Lazy-create and return the singleton crafting config (pk=1)."""
    config, _ = FacetCraftingConfig.objects.get_or_create(pk=1)
    return config


def compute_quality_score(check_result: CheckResult, *, step: int, min_success_level: int) -> int:
    """Quality score = total_points + (success_level - min_success_level) * step.

    Reads only ``total_points`` and ``success_level`` off the CheckResult.
    The graded outcome shifts the score above the crafter's raw skill points.
    """
    bonus = max(0, check_result.success_level - min_success_level) * step
    return check_result.total_points + bonus


@transaction.atomic
def craft_attach_facet(
    *,
    crafter_account: AccountDB,
    crafter_character: ObjectDB,
    item_instance: ItemInstance,
    facet: Facet,
) -> FacetCraftResult:
    """Roll the Enchanting check and, on success, attach ``facet`` at the resolved tier.

    Pre-validates attachability (duplicate/capacity) BEFORE rolling so a full/dup
    item never wastes a check. Ownership is enforced by the view permission.
    Raises CraftingNotConfigured if no CheckType is configured.

    Args:
        crafter_account: The AccountDB applying the facet (stored as applied_by_account).
        crafter_character: The ObjectDB whose traits roll the Enchanting check.
        item_instance: The ItemInstance receiving the facet.
        facet: The Facet to attach.

    Returns:
        FacetCraftResult with attached=True and a resolved quality_tier on success,
        or attached=False with item_facet=None and quality_tier=None on failure.

    Raises:
        CraftingNotConfigured: No CheckType is wired, or no QualityTier rows are seeded.
        FacetCapacityExceeded: The item is at its template's facet_capacity.
        FacetAlreadyAttached: That facet is already present on the item.
    """
    config = get_facet_crafting_config()
    if config.check_type is None:
        raise CraftingNotConfigured

    assert_facet_attachable(item_instance, facet)

    check_result = perform_check(crafter_character, config.check_type, config.base_difficulty)

    if check_result.success_level < config.min_success_level:
        return FacetCraftResult(
            attached=False,
            outcome=check_result.outcome,
            item_facet=None,
            quality_tier=None,
        )

    score = compute_quality_score(
        check_result,
        step=config.success_level_step,
        min_success_level=config.min_success_level,
    )
    tier = QualityTier.for_score(score)
    if tier is None:
        # for_score returns None only when no QualityTier rows exist at all —
        # an unconfigured deployment. Surfaced as CraftingNotConfigured.
        raise CraftingNotConfigured
    item_facet = attach_facet_to_item(
        crafter=crafter_account,
        item_instance=item_instance,
        facet=facet,
        attachment_quality_tier=tier,
    )
    return FacetCraftResult(
        attached=True,
        outcome=check_result.outcome,
        item_facet=item_facet,
        quality_tier=tier,
    )


@transaction.atomic
def craft_attach_style(
    *,
    crafter_account: AccountDB,
    crafter_character: ObjectDB,
    item_instance: ItemInstance,
    style: Style,
) -> StyleCraftResult:
    """Roll the Enchanting check and, on success, attach ``style`` at the resolved tier.

    Pre-validates attachability (duplicate/capacity) BEFORE rolling so a full/dup
    item never wastes a check. Ownership is enforced by the view permission.
    Raises CraftingNotConfigured if no CheckType is configured.

    Args:
        crafter_account: The AccountDB applying the style (stored as applied_by_account).
        crafter_character: The ObjectDB whose traits roll the Enchanting check.
        item_instance: The ItemInstance receiving the style.
        style: The Style to attach.

    Returns:
        StyleCraftResult with attached=True and a resolved quality_tier on success,
        or attached=False with item_style=None and quality_tier=None on failure.

    Raises:
        CraftingNotConfigured: No CheckType is wired, or no QualityTier rows are seeded.
        StyleCapacityExceeded: The item is at its template's style_capacity.
        StyleAlreadyAttached: That style is already present on the item.
    """
    config = get_facet_crafting_config()
    if config.check_type is None:
        raise CraftingNotConfigured

    assert_style_attachable(item_instance, style)

    check_result = perform_check(crafter_character, config.check_type, config.base_difficulty)

    if check_result.success_level < config.min_success_level:
        return StyleCraftResult(
            attached=False,
            outcome=check_result.outcome,
            item_style=None,
            quality_tier=None,
        )

    score = compute_quality_score(
        check_result,
        step=config.success_level_step,
        min_success_level=config.min_success_level,
    )
    tier = QualityTier.for_score(score)
    if tier is None:
        # for_score returns None only when no QualityTier rows exist at all —
        # an unconfigured deployment. Surfaced as CraftingNotConfigured.
        raise CraftingNotConfigured
    item_style = attach_style_to_item(
        crafter=crafter_account,
        item_instance=item_instance,
        style=style,
        attachment_quality_tier=tier,
    )
    return StyleCraftResult(
        attached=True,
        outcome=check_result.outcome,
        item_style=item_style,
        quality_tier=tier,
    )
