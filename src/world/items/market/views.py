"""Market read API (#2066): square browse + shop directory.

Read-only viewsets; all mutations dispatch through the market actions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from world.items.market.models import CraftingServiceOffer, MarketSquare
from world.items.market.serializers import (
    MarketSquareSerializer,
    ServiceOfferSerializer,
)

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from evennia.accounts.models import AccountDB
    from rest_framework.request import Request

    from world.scenes.models import Persona


class MarketSquareFilterSet(django_filters.FilterSet):
    realm = django_filters.NumberFilter(field_name="realm_id")

    class Meta:
        model = MarketSquare
        fields = ["realm"]


class MarketSquareViewSet(viewsets.ReadOnlyModelViewSet):
    """Browse market squares with their stalls and live listings."""

    pagination_class = None  # 2026-07 audit: opt out of default paginator (ADR-0138)

    queryset = MarketSquare.objects.prefetch_related(
        "stalls__stock_listings__template",  # noqa: PREFETCH_STRING — no to_attr on SharedMemoryModel (leak)
        "stalls__ware_listings__item_instance",  # noqa: PREFETCH_STRING
        "stalls__ware_listings__seller_persona",  # noqa: PREFETCH_STRING
        "stalls__owner_persona",  # noqa: PREFETCH_STRING
        "stalls__shopkeeper_persona",  # noqa: PREFETCH_STRING
    ).order_by("name")
    serializer_class = MarketSquareSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = MarketSquareFilterSet


class ServiceOfferFilterSet(django_filters.FilterSet):
    recipe_kind = django_filters.CharFilter(field_name="recipe_kind")

    class Meta:
        model = CraftingServiceOffer
        fields = ["recipe_kind"]


def _viewer_persona(request: Request) -> Persona | None:
    """Active persona for the request account's own character, or None (#2995).

    Fail-closed — mirrors ``_active_persona_for_request`` in ``world.assets.views``.
    """
    from world.roster.models import RosterEntry  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    if not request.user.is_authenticated:
        return None
    user = cast("AccountDB", request.user)
    entry = RosterEntry.objects.for_account(user).first()
    if entry is None:
        return None
    return active_persona_for_sheet(entry.character_sheet)


class ServiceOfferViewSet(viewsets.ReadOnlyModelViewSet):
    """The shop directory: standing craft-as-service offers (visit to use).

    Regard-gated (#2995): for a resolvable viewer, an offer is invisible when
    it fails ``_regard_gate_passes`` against the crafter — the EXACT same
    predicate (refusal floor + any authored ``min_regard``) the purchase-time
    gate checks, so a hard-refused buyer never sees an offer they'd bounce
    off at purchase. Visibility = eligibility, no separate rule. An
    unresolvable viewer (no roster tenure) can't have their regard evaluated,
    so only ``min_regard``-authored offers are hidden as a conservative
    default.
    """

    pagination_class = None  # 2026-07 audit: opt out of default paginator (ADR-0138)

    queryset = (
        CraftingServiceOffer.objects.filter(is_active=True)
        .select_related("crafter_persona", "shop_room")
        .order_by("recipe_kind", "fee")
    )
    serializer_class = ServiceOfferSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = ServiceOfferFilterSet

    def get_queryset(self) -> QuerySet[CraftingServiceOffer]:
        from world.items.market.services import _regard_gate_passes  # noqa: PLC0415

        qs = super().get_queryset()
        viewer = _viewer_persona(self.request)
        if viewer is not None:
            # The refusal floor can bite on ANY offer (crafter_persona is
            # always set), not only min_regard-authored ones — check every
            # offer, not just the gated subset.
            hidden_ids = [
                offer.pk
                for offer in qs
                if not _regard_gate_passes(offer.crafter_persona, viewer, offer.min_regard)
            ]
        else:
            hidden_ids = list(qs.filter(min_regard__isnull=False).values_list("pk", flat=True))
        return qs.exclude(pk__in=hidden_ids) if hidden_ids else qs
