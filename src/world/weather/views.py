"""API views for the weather system (#1522)."""

from __future__ import annotations

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from evennia_extensions.models import RoomProfile
from world.weather.serializers import ConditionsRequestSerializer, ConditionsSerializer
from world.weather.services import current_conditions


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
                required=True,
                description="ObjectDB id of the room to read conditions for.",
            )
        ],
        responses=ConditionsSerializer,
    )
    def conditions(self, request: Request) -> Response:
        """GET /conditions/?room_id=<id> — IC time + the weather holding at a room."""
        request_params = ConditionsRequestSerializer(data=request.query_params)
        request_params.is_valid(raise_exception=True)
        room_id = request_params.validated_data["room_id"]
        try:
            profile = RoomProfile.objects.get(objectdb_id=room_id)
        except RoomProfile.DoesNotExist:
            return Response({"detail": "Room not found."}, status=status.HTTP_404_NOT_FOUND)
        summary = current_conditions(profile.objectdb)
        return Response(ConditionsSerializer(summary).data)
