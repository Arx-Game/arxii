"""Building-manager read API (#670 PR2).

Read-only: the manager payload (rooms + exits + budget + tenancies) an
owner's builder canvas renders, the for-room resolver the RoomPanel button
uses, and the public catalogs (room size tiers, decoration templates).
Every mutation flows through the generic action-dispatch endpoint instead
(``POST /api/actions/characters/<id>/dispatch/``, registry backend).

Interior layout is private: the manager detail is owner-gated via the
``LocationOwnership`` cascade (the same ``is_owner`` gate #1470's editor
uses). The for-room resolver leaks only ids and permission booleans.
"""

from __future__ import annotations

from typing import cast

from django.db.models import Prefetch, Q
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from evennia.accounts.models import AccountDB
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from evennia_extensions.models import ObjectDisplayData, RoomProfile, RoomSizeTier
from world.buildings.models import (
    Building,
    ProjectTemplate,
    ProjectTemplatePolishIncrement,
)
from world.buildings.room_services import building_exits, building_for_room, space_used
from world.buildings.serializers import (
    BuildingManagerSerializer,
    CharacterContextRequestSerializer,
    DecorationTemplateSerializer,
    ForRoomResultSerializer,
    RoomSizeTierSerializer,
)
from world.character_sheets.models import CharacterSheet
from world.locations.models import LocationTenancy
from world.locations.services import is_owner, tenancies_for
from world.projects.constants import ProjectKind
from world.roster.models import RosterEntry
from world.scenes.models import Persona
from world.scenes.services import active_persona_for_sheet

_CHARACTER_ID_PARAM = OpenApiParameter(
    name="character_id",
    type=int,
    required=True,
    description="ObjectDB id of the viewing character (must be your own).",
)


def _viewer_persona(request: Request) -> Persona | None:
    """The active persona of the ``?character_id=`` character, if the account plays it."""
    params = CharacterContextRequestSerializer(data=request.query_params)
    params.is_valid(raise_exception=True)
    character_id = params.validated_data["character_id"]
    user = cast(AccountDB, request.user)
    # character_id == character_sheet_id by construction (CharacterSheet.character is a
    # primary-key OneToOne to ObjectDB), so the tenure check doubles as the ownership gate.
    owned = RosterEntry.objects.for_account(user).filter(character_sheet_id=character_id)
    if not owned.exists():
        return None
    sheet = CharacterSheet.objects.filter(pk=character_id).first()
    if sheet is None:
        return None
    return active_persona_for_sheet(sheet)


def _active_tenancies_by_room(building: Building) -> dict[int, list[LocationTenancy]]:
    """Active tenancy rows for every room in the building, keyed by RoomProfile pk.

    Queried standalone (not prefetched onto the SharedMemoryModel room
    profiles) so per-request data never sticks to identity-mapped instances.
    """
    now = timezone.now()
    rows = (
        LocationTenancy.objects.filter(room_profile__area_id=building.area_id)
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gt=now))
        .select_related("tenant_persona")
    )
    by_room: dict[int, list[LocationTenancy]] = {}
    for row in rows:
        by_room.setdefault(row.room_profile_id, []).append(row)
    return by_room


@extend_schema(tags=["buildings"])
class BuildingManagerViewSet(viewsets.ViewSet):
    """Owner-facing building manager reads (#670): layout, budget, tenancies."""

    # Default read shape for spectacular introspection; each method also
    # carries its own @extend_schema (a bare ViewSet has no auto schema).
    serializer_class = BuildingManagerSerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[_CHARACTER_ID_PARAM],
        responses={200: BuildingManagerSerializer},
    )
    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        """GET /api/buildings/manager/<building_id>/ — the full manager payload."""
        persona = _viewer_persona(request)
        if persona is None:
            return Response({"detail": "Character not found."}, status=status.HTTP_404_NOT_FOUND)
        building = (
            Building.objects.select_related("area", "kind", "architectural_style", "entry_room")
            .filter(pk=pk)
            .first()
        )
        if building is None:
            return Response({"detail": "No such building."}, status=status.HTTP_404_NOT_FOUND)
        entry_profile = building.entry_room
        entry_obj = entry_profile.objectdb if entry_profile is not None else None
        if entry_obj is None or not is_owner(persona, entry_obj):
            return Response(
                {"detail": "You don't manage this building."},
                status=status.HTTP_403_FORBIDDEN,
            )

        profiles = list(
            RoomProfile.objects.filter(area_id=building.area_id).select_related("objectdb", "size")
        )
        room_ids = [p.objectdb_id for p in profiles]
        descriptions = {
            row.object_id: row.permanent_description
            for row in ObjectDisplayData.objects.filter(object_id__in=room_ids)
        }
        tenancies = _active_tenancies_by_room(building)
        used = space_used(building)

        payload = {
            "building": {
                "id": building.pk,
                "name": building.area.name,
                "kind": building.kind.name,
                "style": (
                    building.architectural_style.name if building.architectural_style_id else None
                ),
                "space_budget": building.space_budget,
                "space_used": used,
                "space_remaining": max(0, building.space_budget - used),
                "entry_room_id": building.entry_room_id,
                "floors": sorted({p.floor for p in profiles}),
            },
            "rooms": [
                {
                    "id": p.objectdb_id,
                    "name": p.objectdb.db_key,
                    "description": descriptions.get(p.objectdb_id, ""),
                    "is_public": p.is_public,
                    "size_name": p.size.name if p.size_id else None,
                    "size_units": p.size.units if p.size_id else None,
                    "grid_x": p.grid_x,
                    "grid_y": p.grid_y,
                    "floor": p.floor,
                    "is_entry": p.pk == building.entry_room_id,
                    "tenancies": [
                        {
                            "id": t.pk,
                            "tenant_persona_id": t.tenant_persona_id,
                            "tenant_name": str(t.tenant_persona),
                            "is_primary_home": t.is_primary_home,
                            "ends_at": t.ends_at,
                        }
                        for t in tenancies.get(p.pk, [])
                    ],
                }
                for p in profiles
            ],
            "exits": [
                {
                    "id": e.pk,
                    "name": e.db_key,
                    "from_room_id": e.db_location_id,
                    "to_room_id": e.db_destination_id,
                }
                for e in building_exits(building)
            ],
        }
        return Response(BuildingManagerSerializer(payload).data)

    @extend_schema(
        parameters=[_CHARACTER_ID_PARAM],
        responses={200: ForRoomResultSerializer},
    )
    @action(detail=False, methods=["get"], url_path=r"for-room/(?P<room_id>\d+)")
    def for_room(self, request: Request, room_id: str | None = None) -> Response:
        """GET /api/buildings/manager/for-room/<room_id>/ — ids + permission flags only."""
        persona = _viewer_persona(request)
        if persona is None:
            return Response({"detail": "Character not found."}, status=status.HTTP_404_NOT_FOUND)
        profile = RoomProfile.objects.filter(objectdb_id=room_id).select_related("objectdb").first()
        if profile is None:
            return Response({"detail": "No such room."}, status=status.HTTP_404_NOT_FOUND)
        room_obj = profile.objectdb
        building = building_for_room(room_obj)
        my_tenancies = list(tenancies_for(persona, room_obj))
        payload = {
            "building_id": building.pk if building is not None else None,
            "is_owner": is_owner(persona, room_obj),
            "is_tenant": bool(my_tenancies),
            "is_primary_home_here": any(
                t.is_primary_home and t.tenant_persona_id == persona.pk for t in my_tenancies
            ),
        }
        return Response(ForRoomResultSerializer(payload).data)


class BuildingsCatalogPagination(PageNumberPagination):
    """Small admin-authored catalogs; one page covers them in practice."""

    page_size = 50


@extend_schema(tags=["buildings"])
class RoomSizeTierViewSet(viewsets.ReadOnlyModelViewSet):
    """The shared room-size unit ladder (smallest first)."""

    queryset = RoomSizeTier.objects.order_by("units")
    serializer_class = RoomSizeTierSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = BuildingsCatalogPagination
    filter_backends = [SearchFilter]
    search_fields = ["name"]


@extend_schema(tags=["buildings"])
class DecorationTemplateViewSet(viewsets.ReadOnlyModelViewSet):
    """The admin-authored INTERIOR_DESIGN template catalog (public read)."""

    serializer_class = DecorationTemplateSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = BuildingsCatalogPagination
    filter_backends = [SearchFilter]
    search_fields = ["name", "description"]

    def get_queryset(self):
        # to_attr prefetches are safe here: the catalog relations are stable
        # admin-authored data, not per-request values (the leak class to avoid
        # on SharedMemoryModel parents).
        return (
            ProjectTemplate.objects.filter(project_kind=ProjectKind.INTERIOR_DESIGN)
            .prefetch_related(
                Prefetch(
                    "polish_increment_rows",
                    queryset=ProjectTemplatePolishIncrement.objects.select_related("category"),
                    to_attr="prefetched_increments",
                ),
                Prefetch("tier_prerequisites", to_attr="prefetched_tier_prereqs"),
            )
            .order_by("name")
        )
