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


def ensure_builders_guild_clerk_permits_for_house() -> None:
    """Wire House as the BuildingKind on the Builders Guild Clerk's PERMIT offers.

    The Plan 2 npc_services seed creates the offers with empty
    PermitOfferDetails (no kind set). This patches every PERMIT offer
    on the clerk to authorize the House kind so the issue_permit handler
    can run without raising PermitIssuanceError.

    Idempotent — re-running with kind already set is a no-op.
    """
    from world.npc_services.constants import OfferKind  # noqa: PLC0415
    from world.npc_services.models import NPCServiceOffer  # noqa: PLC0415
    from world.npc_services.seeds import BUILDERS_GUILD_CLERK_ROLE_NAME  # noqa: PLC0415

    house = ensure_house_kind()
    clerk_offers = NPCServiceOffer.objects.filter(
        role__name=BUILDERS_GUILD_CLERK_ROLE_NAME, kind=OfferKind.PERMIT
    ).select_related("permit_offer_details")
    for offer in clerk_offers:
        details = offer.permit_offer_details
        if details.building_kind_id != house.pk:
            details.building_kind = house
            details.save(update_fields=["building_kind"])


def ensure_plan_3_seeds() -> None:
    """Convenience: seed everything Plan 3 needs.

    Safe to call multiple times (each component is idempotent via
    ``get_or_create``).
    """
    ensure_building_permit_template()
    ensure_house_kind()
    # Wire House onto Builders Guild Clerk PERMIT offers when they exist.
    # The clerk's npc_services seed creates the offers; this fills in the kind.
    ensure_builders_guild_clerk_permits_for_house()
