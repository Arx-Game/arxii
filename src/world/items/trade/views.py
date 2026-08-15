"""Trade read API (#2990): the negotiation panel's feed.

Read-only — every mutation dispatches through the trade actions
(``actions/definitions/trade.py``), matching the market convention.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import Q, QuerySet
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from world.items.trade.models import TradeSession
from world.items.trade.serializers import TradeSessionSerializer

if TYPE_CHECKING:
    from rest_framework.request import Request

    from world.character_sheets.models import CharacterSheet


def _viewer_sheet(request: Request) -> CharacterSheet | None:
    """The viewer's active ``CharacterSheet``, or ``None`` (fail-closed).

    TradeSession is CharacterSheet-keyed (#684 — the body owns items, not
    the account or a persona), so the read feed scopes to the puppeted
    character's sheet directly — no persona resolution needed.
    """
    try:
        puppet = request.user.puppet
    except AttributeError:
        return None
    if puppet is None:
        return None
    return puppet.character_sheet


class TradeSessionViewSet(viewsets.ReadOnlyModelViewSet):
    """Your open and past trade sessions — never an account-wide or global browse."""

    pagination_class = None
    serializer_class = TradeSessionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> QuerySet[TradeSession]:
        sheet = _viewer_sheet(self.request)
        if sheet is None:
            return TradeSession.objects.none()
        return (
            TradeSession.objects.filter(
                Q(initiator_sheet=sheet) | Q(counterparty_sheet=sheet),
            )
            .select_related("initiator_sheet__character", "counterparty_sheet__character")
            .prefetch_related(
                "item_stakes__item_instance",  # noqa: PREFETCH_STRING — no to_attr (leak)
                "item_stakes__offered_by_sheet__character",  # noqa: PREFETCH_STRING
            )
        )
