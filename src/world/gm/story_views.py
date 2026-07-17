"""GM story-builder read API (#2450). Mutations go through action dispatch."""

from __future__ import annotations

from django.db.models import Count, QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from world.areas.builder_views import WorldBuilderAreaPagination, area_manager_payload
from world.areas.constants import GridOrigin
from world.areas.filters import AreaFilter
from world.areas.models import Area
from world.areas.serializers import (
    WorldBuilderAreaManagerSerializer,
    WorldBuilderAreaSerializer,
)
from world.gm.permissions import IsGMOrStaff
from world.gm.serializers import StoryInstanceSerializer
from world.instances.constants import InstanceStatus
from world.instances.models import InstancedRoom


@extend_schema(tags=["story-builder"])
class StoryBuilderViewSet(viewsets.ReadOnlyModelViewSet):
    """A GM's own story areas (staff: all story areas). Reads only."""

    serializer_class = WorldBuilderAreaSerializer
    permission_classes = [IsGMOrStaff]
    filter_backends = [DjangoFilterBackend]
    filterset_class = AreaFilter
    pagination_class = WorldBuilderAreaPagination

    def get_queryset(self) -> QuerySet[Area]:
        qs = (
            Area.objects.filter(origin=GridOrigin.STORY)
            .annotate(children_count=Count("children"))
            .order_by("name")
        )
        if self.request.user.is_staff:
            return qs
        return qs.filter(story_ownership__gm__account=self.request.user)

    @extend_schema(responses={200: WorldBuilderAreaManagerSerializer})
    @action(detail=True, methods=["get"], url_path="manager")
    def manager(self, request: Request, pk: str | None = None) -> Response:
        payload = area_manager_payload(self.get_object())
        return Response(WorldBuilderAreaManagerSerializer(payload).data)

    @extend_schema(responses={200: StoryInstanceSerializer(many=True)})
    @action(detail=False, methods=["get"], url_path="instances")
    def instances(self, request: Request) -> Response:
        qs = InstancedRoom.objects.filter(status=InstanceStatus.ACTIVE).select_related("room")
        if not request.user.is_staff:
            qs = qs.filter(gm_owner__account=request.user)
        else:
            qs = qs.filter(gm_owner__isnull=False)
        return Response(StoryInstanceSerializer(qs.order_by("-created_at"), many=True).data)
