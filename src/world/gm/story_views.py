"""GM story-builder read API (#2450). Mutations go through action dispatch."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from django.db.models import Count, QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from world.areas.builder_views import WorldBuilderAreaPagination, area_manager_payload
from world.areas.constants import GridOrigin
from world.areas.filters import AreaFilter
from world.areas.models import Area
from world.areas.serializers import WorldBuilderAreaSerializer
from world.gm.filters import StoryRoomGrantFilter
from world.gm.models import StoryRoomGrant
from world.gm.permissions import IsGMOrStaff
from world.gm.serializers import (
    MyStoryGrantSerializer,
    StoryAreaManagerSerializer,
    StoryInstanceSerializer,
)
from world.instances.constants import InstanceStatus
from world.instances.models import InstancedRoom
from world.stories.pagination import LargeResultsSetPagination

if TYPE_CHECKING:
    from collections.abc import Iterable


def _grants_by_room(room_ids: Iterable[int]) -> dict[int, list[str]]:
    """Batch-fetch granted character names, one query, keyed by room pk.

    ``StoryRoomGrant.room_id`` is a ``RoomProfile`` pk, which is the same
    value as the room's ``ObjectDB`` pk (``RoomProfile.objectdb`` is its
    primary key) — the same id used as ``room["id"]`` in
    ``area_manager_payload`` and as ``room_id`` on ``StoryInstanceSerializer``.
    """
    grants_by_room: dict[int, list[str]] = defaultdict(list)
    grants = StoryRoomGrant.objects.filter(room_id__in=room_ids).select_related(
        "character__character"
    )
    for grant in grants:
        char = grant.character.character
        if char is not None:
            grants_by_room[grant.room_id].append(char.db_key)
    return grants_by_room


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

    @extend_schema(responses={200: StoryAreaManagerSerializer})
    @action(detail=True, methods=["get"], url_path="manager")
    def manager(self, request: Request, pk: str | None = None) -> Response:
        payload = area_manager_payload(self.get_object())
        grants_by_room = _grants_by_room(room["id"] for room in payload["rooms"])
        for room in payload["rooms"]:
            room["grants"] = grants_by_room.get(room["id"], [])
        return Response(StoryAreaManagerSerializer(payload).data)

    @extend_schema(responses={200: StoryInstanceSerializer(many=True)})
    @action(detail=False, methods=["get"], url_path="instances", pagination_class=None)
    def instances(self, request: Request) -> Response:
        """A bare array, not paginated — ``pagination_class=None`` makes the schema say so.

        The view never calls ``self.paginate_queryset()`` (a GM has at most a
        handful of active temp rooms), so without this the ViewSet-level
        ``pagination_class`` made drf-spectacular wrongly advertise
        ``PaginatedStoryInstanceList`` for a response that was always a flat list.
        """
        qs = InstancedRoom.objects.filter(status=InstanceStatus.ACTIVE).select_related("room")
        if not request.user.is_staff:
            qs = qs.filter(gm_owner__account=request.user)
        else:
            qs = qs.filter(gm_owner__isnull=False)
        instances = list(qs.order_by("-created_at"))
        grants_by_room = _grants_by_room(inst.room_id for inst in instances)
        serializer = StoryInstanceSerializer(
            instances, many=True, context={"grants_by_room": grants_by_room}
        )
        return Response(serializer.data)


@extend_schema(tags=["story-rooms"])
class MyStoryGrantsViewSet(viewsets.ReadOnlyModelViewSet):
    """A player's own story-room access grants (#2450 Fix 2 — spec Decision 1 web surface).

    Read-only listing backing the player-facing Story Rooms page (frontend
    ``frontend/src/story-rooms/``). Joining/leaving still go through the
    ``join_story_room``/``leave_story_room`` REGISTRY actions
    (``JoinStoryRoomAction``/``LeaveStoryRoomAction``,
    ``actions/definitions/story_builder.py``), dispatched via the generic
    action-dispatch endpoint — this ViewSet never mutates.
    """

    serializer_class = MyStoryGrantSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = StoryRoomGrantFilter
    pagination_class = LargeResultsSetPagination

    def get_queryset(self) -> QuerySet[StoryRoomGrant]:
        return (
            StoryRoomGrant.objects.filter(character__character__db_account=self.request.user)
            .select_related("room__objectdb", "character__character")
            .order_by("-created_at")
        )
