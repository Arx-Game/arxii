from django.db.models import Count, QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ReadOnlyModelViewSet

from evennia_extensions.models import RoomProfile
from world.areas.constants import GridOrigin
from world.areas.filters import AreaFilter, RoomProfileFilter
from world.areas.models import Area
from world.areas.serializers import (
    AreaListSerializer,
    AreaRoomSerializer,
    WhereEntrySerializer,
    WhoEntrySerializer,
)


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
    """Browse the area hierarchy for room selection.

    STORY-origin areas are excluded — those are a GM's own scratch space
    (world.gm.story_views.StoryBuilderViewSet), not part of the canonical
    world an ordinary player browses (#2450).
    """

    serializer_class = AreaListSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend]
    filterset_class = AreaFilter
    pagination_class = AreaPagination

    def get_queryset(self) -> QuerySet[Area]:
        return (
            Area.objects.exclude(origin=GridOrigin.STORY)
            .annotate(children_count=Count("children"))
            .order_by("name")
        )


class RoomProfileViewSet(ReadOnlyModelViewSet):
    """Browse public rooms, filterable by area (includes descendant areas).

    STORY-origin rooms are excluded even when ``is_public=True`` — defense in
    depth alongside the STORY area exclusion above, since a room's own
    ``is_public`` flag says nothing about its area's origin (#2450).
    """

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
            .exclude(area__origin=GridOrigin.STORY)
            .select_related("objectdb", "area")
            .order_by("objectdb__db_key")
        )


class PresenceView(APIView):
    """Online presence for the web `who`/`where` surfaces (#1463).

    GET → ``{"who": [...], "where": [...]}``. ``who`` lists online characters by active
    persona + a coarse idle state; ``where`` lists characters in public rooms with their
    Evennia-colour-coded area path (the frontend renders the colours). Both are read-only.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        from world.areas.services import where_listing  # noqa: PLC0415
        from world.scenes.presence import who_listing  # noqa: PLC0415

        # The requesting account drives quiet-mode exemptions (#1463): people who've gone
        # hidden still show to themselves and to viewers on their allowlist.
        viewer = request.user
        return Response(
            {
                "who": WhoEntrySerializer(who_listing(viewer), many=True).data,
                "where": WhereEntrySerializer(where_listing(viewer), many=True).data,
            }
        )
