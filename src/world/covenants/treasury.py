"""Covenant treasury services (#2992).

Minimal wiring of the OrganizationTreasury that every Covenant's auto-created
Organization already carries (spec on issue #2992): deposits are open to any
active member (core or minor); withdrawal is gated by CovenantRank tier
against ``spend_rank_max`` (default 1 — the Founder tier). The societies-side
generic-org membership services still refuse covenant orgs; covenant treasury
authority derives from CharacterCovenantRole, not OrganizationMembership.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError

from world.covenants.exceptions import (
    CovenantTreasuryTransferError,
    NotAnActiveCovenantMemberError,
    NotAuthorizedToSpendCovenantTreasuryError,
)
from world.currency.services import get_or_create_purse, get_or_create_treasury, transfer

if TYPE_CHECKING:
    from world.covenants.models import CharacterCovenantRole, Covenant
    from world.currency.models import CurrencyTransfer, OrganizationTreasury


def covenant_treasury(covenant: Covenant) -> OrganizationTreasury:
    """The covenant's shared purse — lazy-created on its backing Organization."""
    return get_or_create_treasury(covenant.organization)


def _assert_active(membership: CharacterCovenantRole) -> None:
    if membership.left_at is not None:
        raise NotAnActiveCovenantMemberError


def deposit_covenant_funds(
    *, membership: CharacterCovenantRole, amount: int, reason: str = ""
) -> CurrencyTransfer:
    """Any active member (core or minor) moves coppers purse -> covenant treasury."""
    _assert_active(membership)
    treasury = covenant_treasury(membership.covenant)
    purse = get_or_create_purse(membership.character_sheet)
    try:
        return transfer(
            amount=amount,
            reason=reason or f"covenant deposit to {membership.covenant.name}",
            from_purse=purse,
            to_treasury=treasury,
        )
    except ValidationError as exc:
        raise CovenantTreasuryTransferError from exc


def withdraw_covenant_funds(
    *, membership: CharacterCovenantRole, amount: int, reason: str = ""
) -> CurrencyTransfer:
    """A spend-ranked active member draws coppers treasury -> their purse.

    Authority: ``membership.rank.tier <= treasury.spend_rank_max`` (rank 1 is
    top; default spend_rank_max=1 = Founder tier only). Piloted-only by
    construction — this is action-driven, never automated.
    """
    _assert_active(membership)
    treasury = covenant_treasury(membership.covenant)
    if membership.rank.tier > treasury.spend_rank_max:
        raise NotAuthorizedToSpendCovenantTreasuryError
    purse = get_or_create_purse(membership.character_sheet)
    try:
        return transfer(
            amount=amount,
            reason=reason or f"covenant withdrawal from {membership.covenant.name}",
            from_treasury=treasury,
            to_purse=purse,
        )
    except ValidationError as exc:
        raise CovenantTreasuryTransferError from exc
