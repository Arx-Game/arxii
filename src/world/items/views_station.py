"""Lab station API views (#1234). Mirrors world/magic/views_sanctum.py's shape —
POST actions converge on Action().run() via the two Actions in
actions/definitions/room_features.py.
"""

from __future__ import annotations

from http import HTTPMethod
from typing import cast

from django.shortcuts import get_object_or_404
from evennia.accounts.models import AccountDB
from evennia.objects.models import ObjectDB
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from actions.definitions.room_features import RepairLabStationAction, StartRoomFeatureProjectAction
from world.items.crafting.models import LabStationDetails
from world.items.serializers_station import (
    LabStationDetailsSerializer,
    LabStationInstallSerializer,
    LabStationRepairSerializer,
)
from world.room_features.seeds import ensure_lab_kind

NO_ACTIVE_CHARACTER_DETAIL = "No active character."


class LabStationViewSet(viewsets.ReadOnlyModelViewSet):
    """Status + install/upgrade/repair endpoints for Lab stations."""

    serializer_class = LabStationDetailsSerializer
    permission_classes = [IsAuthenticated]
    queryset = LabStationDetails.objects.select_related("feature_instance")
    lookup_field = "feature_instance_id"
    lookup_value_regex = r"\d+"

    def _resolve_actor(self, request: Request) -> ObjectDB | None:
        """Mirrors world.magic.views_sanctum.SanctumViewSet._resolve_actor."""
        from world.roster.models import RosterEntry  # noqa: PLC0415

        entry = RosterEntry.objects.for_account(cast(AccountDB, request.user)).first()
        if entry is None:
            return None
        return entry.character_sheet.character

    def _dispatch_install_or_upgrade(self, request: Request) -> Response:
        """Shared body for the ``install`` and ``upgrade`` routes.

        Both dispatch the same ``StartRoomFeatureProjectAction`` — the action
        itself distinguishes install vs upgrade by whether an active feature
        instance already exists at a lower level (#1234 Decision 7). Kept as
        one real route per verb (not a bare method alias) so DRF actually
        registers both URLs.
        """
        from evennia_extensions.models import RoomProfile  # noqa: PLC0415

        serializer = LabStationInstallSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = self._resolve_actor(request)
        if actor is None:
            return Response(
                {"detail": NO_ACTIVE_CHARACTER_DETAIL}, status=status.HTTP_400_BAD_REQUEST
            )
        room_profile = get_object_or_404(
            RoomProfile, pk=serializer.validated_data["room_profile_id"]
        )
        result = StartRoomFeatureProjectAction().run(
            actor=actor,
            room_profile=room_profile,
            feature_kind=ensure_lab_kind(),
            target_level=serializer.validated_data["target_level"],
        )
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=[HTTPMethod.POST], url_path="install")
    def install(self, request: Request) -> Response:
        return self._dispatch_install_or_upgrade(request)

    @action(detail=False, methods=[HTTPMethod.POST], url_path="upgrade")
    def upgrade(self, request: Request) -> Response:
        return self._dispatch_install_or_upgrade(request)

    @action(detail=True, methods=[HTTPMethod.POST], url_path="repair")
    def repair(self, request: Request, feature_instance_id: str | None = None) -> Response:
        station = self.get_object()
        serializer = LabStationRepairSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = self._resolve_actor(request)
        if actor is None:
            return Response(
                {"detail": NO_ACTIVE_CHARACTER_DETAIL}, status=status.HTTP_400_BAD_REQUEST
            )
        room_profile = station.feature_instance.room_profile
        result = RepairLabStationAction().run(
            actor=actor,
            room_profile=room_profile,
            restore_points=serializer.validated_data["restore_points"],
        )
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result.data, status=status.HTTP_200_OK)
