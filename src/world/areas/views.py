from django.db.models import Count, QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet

from world.areas.filters import AreaFilter
from world.areas.models import Area
from world.areas.serializers import AreaListSerializer, AreaRoomSerializer
from world.areas.services import get_rooms_in_area


class AreaViewSet(ReadOnlyModelViewSet):
    """Browse the area hierarchy for room selection."""

    serializer_class = AreaListSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend]
    filterset_class = AreaFilter

    def get_queryset(self) -> QuerySet[Area]:
        return Area.objects.annotate(
            children_count=Count("children"),
        ).order_by("name")

    @action(detail=True, methods=["get"])
    def rooms(self, request: Request, pk: int | None = None) -> Response:
        """Return public rooms in this area and all descendant areas."""
        area = self.get_object()
        rooms = get_rooms_in_area(area)
        public_rooms = [r for r in rooms if r.is_public]
        serializer = AreaRoomSerializer(public_rooms, many=True)
        return Response(serializer.data)
