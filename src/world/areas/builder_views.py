"""Staff-only world-builder read API (#2449 Task 4).

Read-only surface behind ``IsAdminUser`` (``request.user.is_staff``): the area
tree (``GET /api/world-builder/areas/``) and the per-area manager payload
(``GET /api/world-builder/areas/<id>/manager/``) the staff canvas renders —
ALL RoomProfiles in the area (private included), unlike the player-facing
``AreaViewSet``/``RoomProfileViewSet`` (world.areas.views — public rooms only,
no staff bookkeeping fields). Every mutation flows through the registry
action-dispatch endpoint instead (``world_builder``-category actions in
``actions/definitions/world_builder.py``) — this is reads only.

Mirrors ``BuildingManagerViewSet.retrieve``'s query batching (one rooms query
with select_related, one display-data query, one exits query) plus two more
bulk (never per-room) queries this payload needs that the owner-facing
manager doesn't: occupant counts and cross-area exit destination areas.
"""

from __future__ import annotations

from django.db.models import Count, Q, QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from evennia.objects.models import ObjectDB
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAdminUser
from rest_framework.request import Request
from rest_framework.response import Response

from evennia_extensions.models import ObjectDisplayData, RoomProfile
from world.areas.constants import UNFINISHED_ROOM_DESC
from world.areas.filters import AreaFilter
from world.areas.grid_services import exits_from_rooms
from world.areas.models import Area
from world.areas.serializers import (
    WorldBuilderAreaManagerSerializer,
    WorldBuilderAreaSerializer,
    WorldBuilderRoomHitSerializer,
)

_CHARACTER_TYPECLASS = "typeclasses.characters.Character"
_EXIT_TYPECLASS = "typeclasses.exits.Exit"


class WorldBuilderAreaPagination(PageNumberPagination):
    """Mirrors ``world.areas.views.AreaPagination`` for the staff area tree.

    Large page size for hierarchical browsing — drill-down naturally limits
    results, so this is a safety cap rather than UX pagination.
    """

    page_size = 200
    page_size_query_param = "page_size"
    max_page_size = 200


def _occupant_counts(room_ids: list[int]) -> dict[int, int]:
    """Character-occupant counts per room, one bulk query (no per-room N+1).

    Mirrors ``world.areas.grid_services.has_character_occupants``'s
    typeclass check, but batched. Exits are excluded in SQL (#3269) — they
    live in rooms too and dominate the contents at grid scale, so fetching
    and type-checking them in Python made every payload rebuild scale with
    exit count. The authoritative subclass-aware check stays in Python for
    the (few) remaining objects.
    """
    counts: dict[int, int] = {}
    contents = ObjectDB.objects.filter(db_location_id__in=room_ids).exclude(
        db_typeclass_path=_EXIT_TYPECLASS
    )
    for obj in contents:
        if obj.is_typeclass(_CHARACTER_TYPECLASS, exact=False):
            counts[obj.db_location_id] = counts.get(obj.db_location_id, 0) + 1
    return counts


def _needs_prose(description: str) -> bool:
    """Whether a room still awaits its prose pass (#3269): empty or stub text."""
    text = description.strip()
    return (
        # PLACEHOLDER is the repo-wide prose-stub marker in free text, not an identifier.
        not text or text == UNFINISHED_ROOM_DESC or "PLACEHOLDER" in text  # noqa: STRING_LITERAL
    )


def _clue_and_anchor_sidecars(
    room_ids: list[int],
) -> tuple[dict[int, list[dict]], dict[int, list[dict]], dict[int, list[dict]]]:
    """Per-room clue/trigger/anchor lists, three bulk queries (no per-room N+1)."""
    from world.clues.models import ClueTrigger, RoomClue  # noqa: PLC0415
    from world.magic.models import PortalAnchor  # noqa: PLC0415

    clues_by_room: dict[int, list[dict]] = {}
    for row in RoomClue.objects.filter(room_profile_id__in=room_ids).select_related("clue"):
        clues_by_room.setdefault(row.room_profile_id, []).append(
            {
                "id": row.pk,
                "clue_name": row.clue.name,
                "clue_slug": row.clue.slug,
                "detect_difficulty": row.detect_difficulty,
                "fixture_key": row.fixture_key,
            }
        )

    triggers_by_room: dict[int, list[dict]] = {}
    for row in ClueTrigger.objects.filter(room_profile_id__in=room_ids).select_related("clue"):
        triggers_by_room.setdefault(row.room_profile_id, []).append(
            {
                "id": row.pk,
                "clue_name": row.clue.name,
                "clue_slug": row.clue.slug,
                "fixture_key": row.fixture_key,
            }
        )

    anchors_by_room: dict[int, list[dict]] = {}
    for row in (
        PortalAnchor.objects.active().filter(room_profile_id__in=room_ids).select_related("kind")
    ):
        anchors_by_room.setdefault(row.room_profile_id, []).append(
            {
                "id": row.pk,
                "kind_name": row.kind.name,
                "name": row.name,
                "fixture_key": row.fixture_key,
            }
        )

    return clues_by_room, triggers_by_room, anchors_by_room


def area_manager_payload(area: Area) -> dict:
    """Area + all rooms + exits for the world-builder/story-builder manager canvas.

    Shared by ``WorldBuilderViewSet.manager`` (#2449, all areas, staff-only) and
    ``StoryBuilderViewSet.manager`` (#2450, STORY areas, GM-owner-or-staff) — the
    payload shape doesn't vary by origin, only the permission gate on the caller
    does. ``rooms`` includes every RoomProfile in the area regardless of
    ``is_public`` — both callers need to see (and select) private rooms too.
    """
    profiles = list(RoomProfile.objects.filter(area_id=area.pk).select_related("objectdb", "size"))
    room_ids = [p.objectdb_id for p in profiles]
    descriptions = {
        row.object_id: row.permanent_description
        for row in ObjectDisplayData.objects.filter(object_id__in=room_ids)
    }
    occupant_counts = _occupant_counts(room_ids)
    clues_by_room, triggers_by_room, anchors_by_room = _clue_and_anchor_sidecars(room_ids)

    exits = list(exits_from_rooms(set(room_ids)).select_related("db_destination"))
    destination_ids = {e.db_destination_id for e in exits if e.db_destination_id is not None}
    destination_areas = dict(
        RoomProfile.objects.filter(objectdb_id__in=destination_ids).values_list(
            "objectdb_id", "area_id"
        )
    )

    return {
        "area": area,
        "rooms": [
            {
                "id": p.objectdb_id,
                "name": p.objectdb.db_key,
                "description": descriptions.get(p.objectdb_id, ""),
                "is_public": p.is_public,
                "is_social_hub": p.is_social_hub,
                "is_outdoor": p.is_outdoor,
                "enclosure": p.enclosure,
                "size_name": p.size.name if p.size_id else None,
                "grid_x": p.grid_x,
                "grid_y": p.grid_y,
                "floor": p.floor,
                "fixture_key": p.fixture_key,
                "origin": p.origin,
                "exported_at": p.exported_at,
                "needs_prose": _needs_prose(descriptions.get(p.objectdb_id, "")),
                "occupant_count": occupant_counts.get(p.objectdb_id, 0),
                "clues": clues_by_room.get(p.objectdb_id, []),
                "clue_triggers": triggers_by_room.get(p.objectdb_id, []),
                "portal_anchors": anchors_by_room.get(p.objectdb_id, []),
            }
            for p in profiles
        ],
        "exits": [
            {
                "id": e.pk,
                "name": e.db_key,
                "from_room_id": e.db_location_id,
                "to_room_id": e.db_destination_id,
                "to_room_name": (
                    e.db_destination.db_key if e.db_destination_id is not None else None
                ),
                "to_area_id": destination_areas.get(e.db_destination_id),
            }
            for e in exits
        ],
    }


@extend_schema(tags=["world-builder"])
class WorldBuilderViewSet(viewsets.ReadOnlyModelViewSet):
    """Staff-only reads for the world-builder canvas (#2449)."""

    serializer_class = WorldBuilderAreaSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend]
    filterset_class = AreaFilter
    pagination_class = WorldBuilderAreaPagination

    def get_queryset(self) -> QuerySet[Area]:
        return Area.objects.annotate(children_count=Count("children")).order_by("name")

    @extend_schema(responses={200: WorldBuilderRoomHitSerializer(many=True)})
    @action(detail=False, methods=["get"], url_path="room-search")
    def room_search(self, request: Request) -> Response:
        """GET /api/world-builder/areas/room-search/?search= — cross-area room lookup (#3269).

        Matches room key or fixture_key, capped at 50 hits — the "where did I
        put the Traitor's Gate" seam for a 400-room grid, also feeding the
        link-rooms pickers.
        """
        # noqa-rationale: one free-text param on a non-queryset action endpoint;
        # a FilterSet needs a queryset-backed list view to attach to.
        term = (request.query_params.get("search") or "").strip()  # noqa: USE_FILTERSET
        if not term:
            return Response([])
        hits = list(
            RoomProfile.objects.filter(
                Q(objectdb__db_key__icontains=term) | Q(fixture_key__icontains=term)
            )
            .select_related("objectdb", "area")
            .order_by("objectdb__db_key")[:50]
        )
        payload = [
            {
                "id": p.objectdb_id,
                "name": p.objectdb.db_key,
                "area_id": p.area_id,
                "area_name": p.area.name if p.area_id else None,
                "floor": p.floor,
                "fixture_key": p.fixture_key,
            }
            for p in hits
        ]
        return Response(WorldBuilderRoomHitSerializer(payload, many=True).data)

    @extend_schema(responses={200: WorldBuilderAreaManagerSerializer})
    @action(detail=True, methods=["get"], url_path="manager")
    def manager(self, request: Request, pk: str | None = None) -> Response:
        """GET /api/world-builder/areas/<id>/manager/ — area + all rooms + exits.

        Unlike ``BuildingManagerViewSet.retrieve``, ``rooms`` includes every
        RoomProfile in the area regardless of ``is_public`` — staff editing
        the canvas needs to see (and select) private rooms too.
        """
        payload = area_manager_payload(self.get_object())
        return Response(WorldBuilderAreaManagerSerializer(payload).data)
