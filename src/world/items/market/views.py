"""Market read API (#2066): square browse + shop directory.

Read-only viewsets; all mutations dispatch through the market actions.
"""

import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from world.items.market.models import CraftingServiceOffer, MarketSquare
from world.items.market.serializers import (
    MarketSquareSerializer,
    ServiceOfferSerializer,
)


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


class ServiceOfferViewSet(viewsets.ReadOnlyModelViewSet):
    """The shop directory: standing craft-as-service offers (visit to use)."""

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
