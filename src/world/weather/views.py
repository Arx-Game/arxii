"""API views for the weather system (#1522)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from evennia_extensions.models import PlayerData, RoomProfile
from world.weather.serializers import ConditionsRequestSerializer, ConditionsSerializer
from world.weather.services import current_conditions

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


def _selected_character_room(request: Request) -> ObjectDB | None:
    """The caller's selected character's current room, or None.

    The Hall's Time plate reads conditions without a live game session, so it
    has no room id to send — but selection is durable server state (#3412,
    ``PlayerData.selected_entry``), so the server can resolve where that
    character stands. Selection is NOT presence: an offside character with no
    location resolves to None and the caller simply gets no weather.
    """
    player_data = PlayerData.objects.filter(account=request.user).first()
    entry = player_data.selected_entry if player_data else None
    if entry is None:
        return None
    character = entry.character_sheet.character
    return character.location if character else None


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
            )
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
            room = _selected_character_room(request)
            if room is None:
                return Response(
                    {"detail": "No room to read conditions for."},
                    status=status.HTTP_404_NOT_FOUND,
                )
        summary = current_conditions(room)
        return Response(ConditionsSerializer(summary).data)
