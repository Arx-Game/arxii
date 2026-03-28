from django.db.models import Count, QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.viewsets import ReadOnlyModelViewSet

from evennia_extensions.models import RoomProfile
from world.areas.filters import AreaFilter, RoomProfileFilter
from world.areas.models import Area
from world.areas.serializers import AreaListSerializer, AreaRoomSerializer


class AreaPagination(PageNumberPagination):
    """Large page size for hierarchical browsing.

    Drill-down navigation naturally limits results (children of one area
    is typically <20), so this acts as a safety cap rather than UX pagination.
    """

    page_size = 200
    page_size_query_param = "page_size"
    max_page_size = 200


class RoomPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


class AreaViewSet(ReadOnlyModelViewSet):
    """Browse the area hierarchy for room selection."""

    serializer_class = AreaListSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend]
    filterset_class = AreaFilter
    pagination_class = AreaPagination

    def get_queryset(self) -> QuerySet[Area]:
        return Area.objects.annotate(
            children_count=Count("children"),
        ).order_by("name")


class RoomProfileViewSet(ReadOnlyModelViewSet):
    """Browse public rooms, filterable by area (includes descendant areas)."""

    serializer_class = AreaRoomSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend]
    filterset_class = RoomProfileFilter
    pagination_class = RoomPagination

    def get_queryset(self) -> QuerySet[RoomProfile]:
        return (
            RoomProfile.objects.filter(
                is_public=True,
            )
            .select_related("objectdb", "area")
            .order_by("objectdb__db_key")
        )
