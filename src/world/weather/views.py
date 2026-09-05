"""API views for the weather system (#1522)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from evennia_extensions.models import RoomProfile
from world.roster.services.selection import character_for_request
from world.weather.serializers import ConditionsRequestSerializer, ConditionsSerializer
from world.weather.services import current_conditions

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


def _acting_character_room(request: Request, entry_id: int | None) -> ObjectDB | None:
    """The acting character's current room, or None.

    The Hall's Time plate reads conditions without a live game session, so it
    has no room id to send. ``entry_id`` is the tab's browsing identity
    (#3479); omitted, the durable selection (#3412) names the character. The
    resolution is NOT presence: a character with no location resolves to None
    and the caller simply gets no weather.
    """
    character = character_for_request(request, entry_id=entry_id)
    if character is None:
        return None
    return character.location


@extend_schema(tags=["weather"])
class WeatherViewSet(viewsets.ViewSet):
    """Read-only weather queries. Weather/IC time are public ambient info (any logged-in player)."""

    serializer_class = ConditionsSerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="room_id",
                type=int,
                required=False,
                description="ObjectDB id of the room to read conditions for. Omitted, the "
                "caller's selected character's current room is used (404 when there is no "
                "selection or the character is nowhere).",
            ),
            OpenApiParameter(
                name="entry_id",
                type=int,
                required=False,
                description="RosterEntry id of one of the caller's own characters to read "
                "for instead of the account's durable selection (per-tab browsing "
                "identity, #3479). 403 for an id that is not the caller's own.",
            ),
        ],
        responses=ConditionsSerializer,
    )
    def conditions(self, request: Request) -> Response:
        """GET /conditions/?room_id=<id> — IC time + the weather holding at a room."""
        request_params = ConditionsRequestSerializer(data=request.query_params)
        request_params.is_valid(raise_exception=True)
        room_id = request_params.validated_data.get("room_id")
        if room_id is not None:
            try:
                room = RoomProfile.objects.get(objectdb_id=room_id).objectdb
            except RoomProfile.DoesNotExist:
                return Response({"detail": "Room not found."}, status=status.HTTP_404_NOT_FOUND)
        else:
            room = _acting_character_room(request, request_params.validated_data.get("entry_id"))
            if room is None:
                return Response(
                    {"detail": "No room to read conditions for."},
                    status=status.HTTP_404_NOT_FOUND,
                )
        summary = current_conditions(room)
        return Response(ConditionsSerializer(summary).data)
