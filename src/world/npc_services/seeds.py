"""Idempotent role + offer seeding helpers.

These functions live here (not in a committed fixture) per repo discipline:
fixtures are gitignored and reserved for data seeding via admin/shared
storage, not version-controlled bootstraps (see #683). Tests use these
helpers directly from setUp; staff tooling will eventually call them too.

The Builders Guild Clerk is the first concrete `NPCRole` and ships with a
small menu of permit-issuance offers. Plan 3 (#668) wires the real
PermitOfferDetails fields + ward eligibility rules; Plan 2 ships the
offers with empty eligibility_rule so the framework is end-to-end
testable today.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.npc_services.constants import DrawMode, OfferKind
from world.npc_services.models import (
    NPCRole,
    NPCServiceOffer,
    PermitOfferDetails,
)

if TYPE_CHECKING:
    from world.buildings.models import BuildingKind

BUILDERS_GUILD_CLERK_ROLE_NAME = "Builders Guild Clerk"


_CLERK_OFFER_LABELS: frozenset[str] = frozenset(
    {
        "Apply for a Cottage permit",
        "Apply for a House permit",
        "Apply for a Tavern permit",
        "Apply for a Shop permit",
        "Apply for a Workshop permit",
        "Apply for a Guild Hall permit",
        "Apply for a Warehouse permit",
        "Negotiate a discount on permit fees",
        "Request expedited processing",
    }
)


def ensure_builders_guild_clerk_role() -> NPCRole:
    """Get-or-create the Builders Guild Clerk role + its permit offers.

    Idempotent. Safe to call from test setUp, app startup, or staff
    tooling. Each PERMIT offer is explicitly wired to a BuildingKind
    via ``PermitOfferDetails.building_kind``. Old-label offers from
    prior seed versions are cleaned up on each invocation.
    """
    from world.buildings.models import BuildingKind  # noqa: PLC0415
    from world.buildings.seeds import (  # noqa: PLC0415
        ensure_house_kind,
        ensure_urban_building_kinds,
    )

    ensure_urban_building_kinds()
    ensure_house_kind()

    role, _ = NPCRole.objects.get_or_create(
        name=BUILDERS_GUILD_CLERK_ROLE_NAME,
        defaults={
            "description": (
                "Issues building permits on behalf of the Builders Guild. "
                "Manages ward-level eligibility and negotiated permit terms."
            ),
            "default_description_template": (
                "A clerk of the Builders Guild sits behind a worn oak desk, "
                "ledgers stacked in tidy columns."
            ),
            "default_rapport_starting_value": 0,
        },
    )

    # Idempotent cleanup: delete any offers on this role whose labels
    # are not in the current expected set (handles migration from old
    # seed labels like "Apply for a small residential permit").
    NPCServiceOffer.objects.filter(role=role).exclude(label__in=_CLERK_OFFER_LABELS).delete()

    _ensure_offer(
        role=role,
        label="Apply for a Cottage permit",
        building_kind=BuildingKind.objects.get(name="Cottage"),
        max_target_size=2,
    )
    _ensure_offer(
        role=role,
        label="Apply for a House permit",
        building_kind=BuildingKind.objects.get(name="House"),
        max_target_size=3,
    )
    _ensure_offer(
        role=role,
        label="Apply for a Tavern permit",
        building_kind=BuildingKind.objects.get(name="Tavern"),
        max_target_size=5,
    )
    _ensure_offer(
        role=role,
        label="Apply for a Shop permit",
        building_kind=BuildingKind.objects.get(name="Shop"),
        max_target_size=4,
    )
    _ensure_offer(
        role=role,
        label="Apply for a Workshop permit",
        building_kind=BuildingKind.objects.get(name="Workshop"),
        max_target_size=4,
    )
    _ensure_offer(
        role=role,
        label="Apply for a Guild Hall permit",
        building_kind=BuildingKind.objects.get(name="Guild Hall"),
        max_target_size=6,
    )
    _ensure_offer(
        role=role,
        label="Apply for a Warehouse permit",
        building_kind=BuildingKind.objects.get(name="Warehouse"),
        max_target_size=5,
    )
    _ensure_offer(
        role=role,
        label="Negotiate a discount on permit fees",
        rapport_requirement=5,
        is_final=False,
        rapport_delta_success=2,
        rapport_delta_failure=-3,
    )
    _ensure_offer(
        role=role,
        label="Request expedited processing",
        rapport_requirement=10,
    )
    return role


def _ensure_offer(
    role: NPCRole,
    label: str,
    *,
    building_kind: BuildingKind | None = None,
    max_target_size: int | None = None,
    **overrides: object,
) -> NPCServiceOffer:
    """Inner helper: idempotent (role, label)-keyed offer + details row.

    ``overrides`` accepts any NPCServiceOffer field (rapport_requirement,
    is_final, rapport_delta_success/failure, etc.). Defaults to a final
    PERMIT MENU offer with zero rapport requirement and zero deltas.

    When ``building_kind`` is provided, it is set on the offer's
    ``PermitOfferDetails`` row at creation time. When ``max_target_size``
    is provided, it overrides the default (10) on the details row.
    """
    defaults: dict[str, object] = {
        "kind": OfferKind.PERMIT,
        "draw_mode": DrawMode.MENU,
        "eligibility_rule": {},  # Plan 3 fills in ward-permit predicates.
        "rapport_requirement": 0,
        "is_final": True,
        "rapport_delta_success": 0,
        "rapport_delta_failure": 0,
    }
    defaults.update(overrides)
    offer, created = NPCServiceOffer.objects.get_or_create(
        role=role, label=label, defaults=defaults
    )
    if created:
        details_defaults: dict[str, object] = {}
        if building_kind is not None:
            details_defaults["building_kind"] = building_kind
        if max_target_size is not None:
            details_defaults["default_max_target_size"] = max_target_size
        PermitOfferDetails.objects.create(offer=offer, **details_defaults)
    return offer
