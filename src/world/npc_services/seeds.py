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

from world.npc_services.constants import DrawMode, OfferKind
from world.npc_services.models import (
    NPCRole,
    NPCServiceOffer,
    PermitOfferDetails,
)

BUILDERS_GUILD_CLERK_ROLE_NAME = "Builders Guild Clerk"


def ensure_builders_guild_clerk_role() -> NPCRole:
    """Get-or-create the Builders Guild Clerk role + its permit offers.

    Idempotent. Safe to call from test setUp, app startup, or staff
    tooling. Offers are created with empty ``eligibility_rule`` (Plan 3
    fills in the real ward-permit predicate); each offer gets a
    ``PermitOfferDetails`` row so the per-kind details model is wired.
    """
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
    _ensure_offer(
        role=role,
        label="Apply for a small residential permit",
        rapport_requirement=0,
    )
    _ensure_offer(
        role=role,
        label="Apply for a workshop permit",
        rapport_requirement=0,
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


def _ensure_offer(role: NPCRole, label: str, **overrides: object) -> NPCServiceOffer:
    """Inner helper: idempotent (role, label)-keyed offer + details row.

    ``overrides`` accepts any NPCServiceOffer field (rapport_requirement,
    is_final, rapport_delta_success/failure, etc.). Defaults to a final
    PERMIT MENU offer with zero rapport requirement and zero deltas.
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
        PermitOfferDetails.objects.create(offer=offer)
    return offer
