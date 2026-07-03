"""Lab station API views (#1234). Mirrors world/magic/views_sanctum.py's shape —
POST actions converge on Action().run() via the two Actions in
actions/definitions/room_features.py.
"""

from __future__ import annotations

from http import HTTPMethod

from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from evennia.objects.models import ObjectDB
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from actions.definitions.room_features import RepairLabStationAction, StartRoomFeatureProjectAction
from world.items.crafting.models import LabStationDetails
from world.items.filters import LabStationFilter
from world.items.serializers_station import (
    LabStationDetailsSerializer,
    LabStationInstallSerializer,
    LabStationRepairResultSerializer,
    LabStationRepairSerializer,
    RoomFeatureProjectStartResultSerializer,
)
from world.items.views import ItemTemplatePagination
from world.magic.services.auth import _resolve_actor_sheet
from world.room_features.seeds import ensure_lab_kind


class LabStationViewSet(viewsets.ReadOnlyModelViewSet):
    """Status + install/upgrade/repair endpoints for Lab stations.

    ``pagination_class``/``filter_backends`` on the list endpoint (#1234
    whole-branch review finding) — reuses ``ItemTemplatePagination`` (the
    repo's shared page-size-50 convention, already reused by
    ``FashionPresentationViewSet``) rather than a bespoke pagination class;
    ``LabStationFilter`` lets callers scope the list to a single room.
    """

    serializer_class = LabStationDetailsSerializer
    permission_classes = [IsAuthenticated]
    queryset = LabStationDetails.objects.select_related("feature_instance").order_by(
        "feature_instance_id"
    )
    lookup_field = "feature_instance_id"
    lookup_value_regex = r"\d+"
    pagination_class = ItemTemplatePagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = LabStationFilter

    def _resolve_actor(self, request: Request) -> ObjectDB:
        """Resolve the acting character via the shared alt-guard helper.

        Mirrors ``FashionPresentationViewSet.create`` / ``FashionJudgementViewSet.create``
        (``world/items/views.py``) — delegates to
        ``world.magic.services.auth._resolve_actor_sheet`` rather than picking an
        arbitrary active tenure via ``RosterEntry.objects.for_account(...).first()``.
        An account with more than one simultaneously-active character (alts) could
        otherwise resolve to a character with no standing over the target room,
        producing a spurious 400 even when another of the account's active
        characters does have standing.

        Zero active tenures raises ``PermissionDenied`` (403); multiple active
        tenures without an explicit ``actor_sheet_id`` in the POST body raises
        ``ValidationError`` (400) rather than silently guessing. Both propagate
        to DRF's default exception handling — same as the ``views.py`` usages,
        no local catch here.
        """
        sheet = _resolve_actor_sheet(request, body_key="actor_sheet_id")
        return sheet.character

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
        return Response(
            RoomFeatureProjectStartResultSerializer(result.data).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(responses={201: RoomFeatureProjectStartResultSerializer})
    @action(detail=False, methods=[HTTPMethod.POST], url_path="install")
    def install(self, request: Request) -> Response:
        return self._dispatch_install_or_upgrade(request)

    @extend_schema(responses={201: RoomFeatureProjectStartResultSerializer})
    @action(detail=False, methods=[HTTPMethod.POST], url_path="upgrade")
    def upgrade(self, request: Request) -> Response:
        return self._dispatch_install_or_upgrade(request)

    @extend_schema(responses={200: LabStationRepairResultSerializer})
    @action(detail=True, methods=[HTTPMethod.POST], url_path="repair")
    def repair(self, request: Request, feature_instance_id: str | None = None) -> Response:
        station = self.get_object()
        serializer = LabStationRepairSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = self._resolve_actor(request)
        room_profile = station.feature_instance.room_profile
        result = RepairLabStationAction().run(
            actor=actor,
            room_profile=room_profile,
            restore_points=serializer.validated_data["restore_points"],
        )
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            LabStationRepairResultSerializer(result.data).data,
            status=status.HTTP_200_OK,
        )
