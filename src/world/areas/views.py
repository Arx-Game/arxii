from django.db.models import Count, QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet

from evennia_extensions.models import RoomProfile
from world.areas.filters import AreaFilter
from world.areas.models import Area, AreaClosure
from world.areas.serializers import AreaListSerializer, AreaRoomSerializer


class AreaPagination(PageNumberPagination):
    """Large page size for hierarchical browsing.

    Drill-down navigation naturally limits results (children of one area
    is typically <20), so this acts as a safety cap rather than UX pagination.
    """

    page_size = 200
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

    @action(detail=True, methods=["get"])
    def rooms(self, request: Request, pk: int | None = None) -> Response:
        """Return public rooms in this area and all descendant areas."""
        area = self.get_object()
        area_pks = list(
            AreaClosure.objects.filter(ancestor_id=area.pk).values_list("descendant_id", flat=True)
        )
        rooms = RoomProfile.objects.filter(area_id__in=area_pks, is_public=True).select_related(
            "objectdb", "area"
        )
        serializer = AreaRoomSerializer(rooms, many=True)
        return Response(serializer.data)
