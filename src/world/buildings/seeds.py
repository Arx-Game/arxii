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
            "is_residential": True,
        },
    )
    return kind


# PLACEHOLDER magnitudes (#670) — ratified super-linear curve (one big build ≈ 2× two
# half-size builds); absolute values await the economy/tuning pass. Admin-editable rows.
BUILDING_SIZE_TIERS: tuple[tuple[int, str, int], ...] = (
    (1, "Hut", 50),
    (2, "Cottage", 125),
    (3, "House", 250),
    (4, "Manor", 600),
    (5, "Estate", 1250),
    (6, "Palace", 2500),
    (7, "Citadel", 5000),
)


def ensure_building_size_tiers() -> None:
    """Get-or-create the building-size budget ladder (#670)."""
    from world.buildings.models import BuildingSizeTier  # noqa: PLC0415

    for tier, name, space_budget in BUILDING_SIZE_TIERS:
        BuildingSizeTier.objects.get_or_create(
            tier=tier, defaults={"name": name, "space_budget": space_budget}
        )


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
    ensure_building_size_tiers()
    # Room-size ladder (#670) lives in evennia_extensions but construction depends
    # on it for the entry room's default size — seed it alongside.
    from evennia_extensions.seeds import ensure_room_size_tiers  # noqa: PLC0415

    ensure_room_size_tiers()
