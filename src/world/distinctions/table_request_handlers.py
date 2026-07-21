"""Completion handlers for distinction-kind table update requests (#2607).

Registered into ``world.gm.request_handlers`` from ``DistinctionsConfig.ready``.
A handler runs when a member COMPLETES an approved request: it charges XP on the
benefit direction (via the ``spend_xp_on_gift_unlock`` template — resolve the
account XP tracker, check, spend, write an ``XPTransaction`` ledger row) and
then grants or revokes the distinction.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from world.distinctions.services import (
    distinction_change_xp_cost,
    grant_distinction,
    revoke_distinction,
)
from world.distinctions.types import DistinctionOrigin

if TYPE_CHECKING:
    from world.gm.models import TableUpdateRequest


class XPInsufficient(Exception):
    """The completing member cannot afford the XP cost of their approved change."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.user_message = message


def _charge_change_xp(request: TableUpdateRequest, *, removing: bool) -> None:
    from world.progression.models.rewards import XPTransaction  # noqa: PLC0415
    from world.progression.services.awards import get_or_create_xp_tracker  # noqa: PLC0415
    from world.progression.types import ProgressionReason  # noqa: PLC0415

    details = request.distinction_change_details
    cost = distinction_change_xp_cost(details.distinction, rank=details.rank, removing=removing)
    if cost == 0:
        return
    sheet = request.membership.persona.character_sheet
    account = sheet.character.account
    if account is None:
        raise XPInsufficient("No linked account; cannot spend XP.")
    tracker = get_or_create_xp_tracker(account)
    if not tracker.can_spend(cost):
        raise XPInsufficient(
            f"Need {cost} XP to complete this change, have {tracker.current_available}."
        )
    tracker.spend_xp(cost)
    XPTransaction.objects.create(
        account=account,
        amount=-cost,
        reason=ProgressionReason.TABLE_REQUEST,
        description=f"Distinction change: {details.distinction.name}",
        character=sheet.character,
        gm=None,
    )


@transaction.atomic
def complete_distinction_add(request: TableUpdateRequest) -> None:
    details = request.distinction_change_details
    _charge_change_xp(request, removing=False)
    grant_distinction(
        request.membership.persona.character_sheet,
        details.distinction,
        origin=DistinctionOrigin.GM_AWARD,
        rank=details.rank,
        source_description="table request",
    )


@transaction.atomic
def complete_distinction_remove(request: TableUpdateRequest) -> None:
    from world.distinctions.models import CharacterDistinction  # noqa: PLC0415

    details = request.distinction_change_details
    _charge_change_xp(request, removing=True)
    character_distinction = CharacterDistinction.objects.get(
        character=request.membership.persona.character_sheet,
        distinction=details.distinction,
    )
    revoke_distinction(character_distinction)
