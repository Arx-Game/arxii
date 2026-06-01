"""Idempotent seed helpers for the buildings system.

Per repo discipline (#683): seeds live in code, called via
``get_or_create``. NOT a committed fixture.

Plan 3 seeds:
- The ``BuildingPermit`` ItemTemplate row (one row; the issue_permit
  effect handler instantiates copies for each issued permit)
- The ``House`` BuildingKind row
"""

from __future__ import annotations

from world.buildings.models import BuildingKind
from world.buildings.services import BUILDING_PERMIT_TEMPLATE_NAME

HOUSE_KIND_NAME = "House"


def ensure_building_permit_template():
    """Get-or-create the BuildingPermit ItemTemplate row.

    The permit is a consumable item (max_charges=1). Each issued permit
    is an ItemInstance of this template, decorated by a
    BuildingPermitDetails row carrying the IC parameters.
    """
    from world.items.models import ItemTemplate  # noqa: PLC0415

    template, _ = ItemTemplate.objects.get_or_create(
        name=BUILDING_PERMIT_TEMPLATE_NAME,
        defaults={
            "description": (
                "An authorization to construct a building of a specific "
                "kind in a specific ward. Activate the permit at an outdoor "
                "site within an approved ward to open the construction flow."
            ),
            "is_consumable": True,
            "max_charges": 1,
            "value": 0,
        },
    )
    return template


def ensure_house_kind() -> BuildingKind:
    """Get-or-create the House BuildingKind row (Plan 3's MVP kind)."""
    kind, _ = BuildingKind.objects.get_or_create(
        name=HOUSE_KIND_NAME,
        defaults={
            "description": (
                "A residential dwelling. Plan 3's MVP BuildingKind; other "
                "kinds (manors, taverns, ships, ritual sites, etc.) land "
                "via content authoring."
            ),
            "rooms_per_size_tier": 20,
            "is_residential": True,
        },
    )
    return kind


def ensure_default_kind_on_permit_offers() -> None:
    """Set House as default BuildingKind on every PERMIT offer missing one.

    Plan 2's npc_services seed creates PermitOfferDetails rows without a
    building_kind set. Without it, ``issue_permit`` raises
    ``PermitIssuanceError`` — so any role with PERMIT offers (Builders
    Guild Clerk today, future Cult Leader / Sailors' Guild / etc.) needs
    a kind wired before its handlers can run. Patching ALL PERMIT offers
    (not just the clerk's) means future roles inherit a sensible default
    when content authors forget to set one.

    Idempotent — only patches rows where ``building_kind_id IS NULL``.
    """
    from world.npc_services.constants import OfferKind  # noqa: PLC0415
    from world.npc_services.models import NPCServiceOffer  # noqa: PLC0415

    house = ensure_house_kind()
    unwired = NPCServiceOffer.objects.filter(
        kind=OfferKind.PERMIT,
        permit_offer_details__building_kind__isnull=True,
    ).select_related("permit_offer_details")
    for offer in unwired:
        details = offer.permit_offer_details
        details.building_kind = house
        details.save(update_fields=["building_kind"])


# Back-compat alias for callers using the old, clerk-specific name.
ensure_builders_guild_clerk_permits_for_house = ensure_default_kind_on_permit_offers


def ensure_plan_3_seeds() -> None:
    """Convenience: seed everything Plan 3 needs.

    Safe to call multiple times (each component is idempotent).
    """
    ensure_building_permit_template()
    ensure_house_kind()
    ensure_default_kind_on_permit_offers()
