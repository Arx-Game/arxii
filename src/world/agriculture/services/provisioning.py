"""Food provisioning services — army mobilization and ship crew per leg."""

from __future__ import annotations

import logging

from django.db import transaction

from world.agriculture.models import FoodStockpile
from world.agriculture.services.production import get_food_config

logger = logging.getLogger(__name__)


@transaction.atomic
def provision_army(covenant) -> float:
    """Compute and deduct army food provisioning at mobilization.

    Counts engaged covenant members, computes the food needed
    (``engaged_count × config.army_food_per_member``), and deducts from
    the covenant's org's domains' ``FoodStockpile`` reserves. Stores the
    resulting ratio (0.0–1.0) on ``covenant.provisioning_ratio``.

    Args:
        covenant: The ``Covenant`` being mobilized.

    Returns:
        The provisioning ratio (0.0–1.0). 1.0 means fully provisioned
        (or no army to feed). 0.0 means no food at all.
    """
    config = get_food_config()
    engaged_count = covenant.memberships.filter(engaged=True, left_at__isnull=True).count()

    if engaged_count == 0:
        ratio = 1.0
        covenant.provisioning_ratio = ratio
        covenant.save(update_fields=["provisioning_ratio"])
        return ratio

    needed = engaged_count * config.army_food_per_member
    domains = list(covenant.organization.domains.all())

    stockpiles: list[FoodStockpile] = []
    total_available = 0
    for domain in domains:
        try:
            stockpile = domain.food_stockpile
        except FoodStockpile.DoesNotExist:
            continue
        if stockpile.stored > 0:
            stockpiles.append(stockpile)
            total_available += stockpile.stored

    if total_available >= needed:
        ratio = 1.0
        _deduct_proportional(stockpiles, total_available, needed)
    else:
        ratio = total_available / needed if needed > 0 else 1.0
        for sp in stockpiles:
            sp.stored = 0
            sp.save(update_fields=["stored"])

    covenant.provisioning_ratio = ratio
    covenant.save(update_fields=["provisioning_ratio"])
    _emit_provisioning_message(covenant, ratio, needed, total_available)
    return ratio


def _deduct_proportional(
    stockpiles: list[FoodStockpile], total_available: int, needed: int
) -> None:
    """Deduct ``needed`` food proportionally across stockpiles."""
    remaining = needed
    for i, sp in enumerate(stockpiles):
        if i == len(stockpiles) - 1:
            # Last stockpile gets the remainder to avoid rounding gaps.
            deduct = remaining
        else:
            deduct = round(needed * (sp.stored / total_available))
            remaining -= deduct
        sp.stored = max(0, sp.stored - deduct)
        sp.save(update_fields=["stored"])


def _emit_provisioning_message(covenant, ratio: float, needed: int, total_available: int) -> None:
    """Send a narrative message to engaged members about provisioning status."""
    from world.narrative.constants import NarrativeCategory  # noqa: PLC0415
    from world.narrative.services import send_narrative_message  # noqa: PLC0415

    sheets = [
        m.character_sheet
        for m in covenant.memberships.filter(engaged=True, left_at__isnull=True).select_related(
            "character_sheet"
        )
    ]
    if not sheets:
        return

    if ratio >= 1.0:
        body = (
            f"Provisions for {covenant.name} are secured — "
            f"{needed} food mustered from the domain stockpiles."
        )
    else:
        body = (
            f"Provisions for {covenant.name} fall short — only "
            f"{total_available} of {needed} needed food mustered. "
            f"The army fights at {int(ratio * 100)}% supply."
        )

    send_narrative_message(
        recipients=sheets,
        body=body,
        category=NarrativeCategory.COVENANT,
    )


@transaction.atomic
def provision_ship_leg(voyage) -> float:
    """Compute and deduct ship crew food for one voyage leg.

    Resolves the ship's owner persona -> their orgs (where they hold a
    leadership rank with ``can_manage_ranks=True``) -> those orgs' domains
    -> ``FoodStockpile`` rows. Computes
    ``needed = ship.crew_capacity * config.crew_food_per_leg``. Deducts
    proportionally using ``_deduct_proportional``. Stores the resulting
    ratio (0.0-1.0) on ``voyage.provisioning_ratio``.

    Args:
        voyage: The ``Voyage`` whose ship needs provisioning.

    Returns:
        The provisioning ratio (0.0-1.0). 1.0 means fully provisioned
        (or ``crew_capacity == 0``). 0.0 means no food at all.
    """
    from world.societies.models import OrganizationMembership  # noqa: PLC0415

    ship = voyage.ship
    if ship is None:
        return 1.0

    config = get_food_config()
    needed = ship.crew_capacity * config.crew_food_per_leg

    if needed == 0:
        ratio = 1.0
        voyage.provisioning_ratio = ratio
        voyage.save(update_fields=["provisioning_ratio"])
        return ratio

    owner_persona = ship.building.owner_persona
    if owner_persona is None:
        ratio = 0.0
        voyage.provisioning_ratio = ratio
        voyage.save(update_fields=["provisioning_ratio"])
        _emit_ship_provisioning_message(voyage, ratio, needed, 0)
        return ratio

    # Find orgs where the owner holds a leadership rank.
    leader_org_ids = list(
        OrganizationMembership.objects.filter(
            persona=owner_persona,
            left_at__isnull=True,
            exiled_at__isnull=True,
            rank__can_manage_ranks=True,
        ).values_list("organization_id", flat=True)
    )

    stockpiles: list[FoodStockpile] = list(
        FoodStockpile.objects.filter(domain__owner_org_id__in=leader_org_ids, stored__gt=0)
    )
    total_available = sum(sp.stored for sp in stockpiles)

    if total_available >= needed:
        ratio = 1.0
        _deduct_proportional(stockpiles, total_available, needed)
    else:
        ratio = total_available / needed if needed > 0 else 1.0
        for sp in stockpiles:
            sp.stored = 0
            sp.save(update_fields=["stored"])

    voyage.provisioning_ratio = ratio
    voyage.save(update_fields=["provisioning_ratio"])
    _emit_ship_provisioning_message(voyage, ratio, needed, total_available)
    return ratio


def _emit_ship_provisioning_message(
    voyage, ratio: float, needed: int, total_available: int
) -> None:
    """Send a narrative message to voyage participants about provisioning."""
    from world.narrative.constants import NarrativeCategory  # noqa: PLC0415
    from world.narrative.services import send_narrative_message  # noqa: PLC0415

    sheets = [
        p.persona.character_sheet
        for p in voyage.participants.filter(left_at__isnull=True).select_related(
            "persona__character_sheet"
        )
    ]
    if not sheets:
        return

    if ratio >= 1.0:
        body = (
            f"Provisions for the voyage are secured -- "
            f"{needed} food mustered from the domain stockpiles."
        )
    elif ratio > 0.0:
        body = (
            f"Provisions fall short -- only "
            f"{total_available} of {needed} food mustered. "
            f"The crew sails at {int(ratio * 100)}% supply."
        )
    else:
        body = "The domain larders are bare -- no food for the crew. The ship cannot sail."

    send_narrative_message(
        recipients=sheets,
        body=body,
        category=NarrativeCategory.SYSTEM,
    )
