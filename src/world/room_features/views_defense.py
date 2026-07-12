"""Defense (bars/ward/alarm) web surfaces (#2177). Mirrors
world/items/views_station.py's shape — POST actions converge on
Action().run() via StartDefenseInstallationAction/FundRoomWardAction.
"""

from __future__ import annotations

from http import HTTPMethod

from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from actions.definitions.room_features import FundRoomWardAction, StartDefenseInstallationAction
from world.items.views import ItemTemplatePagination
from world.magic.services.auth import _resolve_actor_sheet
from world.room_features.filters import ExitBarsFilter, RoomAlarmFilter, RoomWardFilter
from world.room_features.models import ExitBarsDetails, RoomAlarmDetails, RoomWardDetails
from world.room_features.serializers_defense import (
    DefenseInstallResultSerializer,
    DefenseInstallSerializer,
    ExitBarsDetailsSerializer,
    FundWardResultSerializer,
    FundWardSerializer,
    RoomAlarmDetailsSerializer,
    RoomWardDetailsSerializer,
)


class ExitBarsViewSet(viewsets.ReadOnlyModelViewSet):
    """Status endpoint for installed exit bars.

    ``pagination_class``/``filter_backends`` (#2177 whole-branch review,
    Important #4) mirror ``world.items.views_station.LabStationViewSet`` --
    reuse the repo's shared page-size-50 convention (``ItemTemplatePagination``)
    and let a caller scope the list to a single exit via ``ExitBarsFilter``
    rather than listing every installation in the game unscoped.
    """

    serializer_class = ExitBarsDetailsSerializer
    permission_classes = [IsAuthenticated]
    queryset = ExitBarsDetails.objects.active().order_by("exit_profile_id")
    lookup_field = "exit_profile_id"
    lookup_value_regex = r"\d+"
    pagination_class = ItemTemplatePagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = ExitBarsFilter


class RoomWardViewSet(viewsets.ReadOnlyModelViewSet):
    """Status endpoint for installed room wards. See ``ExitBarsViewSet`` docstring."""

    serializer_class = RoomWardDetailsSerializer
    permission_classes = [IsAuthenticated]
    queryset = RoomWardDetails.objects.active().order_by("room_profile_id")
    lookup_field = "room_profile_id"
    lookup_value_regex = r"\d+"
    pagination_class = ItemTemplatePagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = RoomWardFilter


class RoomAlarmViewSet(viewsets.ReadOnlyModelViewSet):
    """Status endpoint for installed room alarms. See ``ExitBarsViewSet`` docstring."""

    serializer_class = RoomAlarmDetailsSerializer
    permission_classes = [IsAuthenticated]
    queryset = RoomAlarmDetails.objects.active().order_by("room_profile_id")
    lookup_field = "room_profile_id"
    lookup_value_regex = r"\d+"
    pagination_class = ItemTemplatePagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = RoomAlarmFilter


class DefenseInstallViewSet(viewsets.ViewSet):
    """Write-only install/upgrade/fund routes spanning all three defense kinds."""

    permission_classes = [IsAuthenticated]

    def _resolve_actor(self, request: Request):
        sheet = _resolve_actor_sheet(request, body_key="actor_sheet_id")
        return sheet.character

    def _dispatch_install_or_upgrade(self, request: Request) -> Response:
        serializer = DefenseInstallSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = self._resolve_actor(request)
        kwargs = {
            "defense_kind": serializer.validated_data["defense_kind"],
            "target_level": serializer.validated_data["target_level"],
        }
        if "exit_id" in serializer.validated_data:  # noqa: STRING_LITERAL
            kwargs["exit_id"] = serializer.validated_data["exit_id"]
        if "resonance_id" in serializer.validated_data:  # noqa: STRING_LITERAL
            from world.magic.models.affinity import Resonance  # noqa: PLC0415

            kwargs["resonance"] = Resonance.objects.filter(
                pk=serializer.validated_data["resonance_id"]
            ).first()
        if "reaction_condition_id" in serializer.validated_data:  # noqa: STRING_LITERAL
            kwargs["reaction_condition_id"] = serializer.validated_data["reaction_condition_id"]
        if "reaction_damage_amount" in serializer.validated_data:  # noqa: STRING_LITERAL
            kwargs["reaction_damage_amount"] = serializer.validated_data["reaction_damage_amount"]
        result = StartDefenseInstallationAction().run(actor=actor, **kwargs)
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            DefenseInstallResultSerializer(result.data).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(responses={201: DefenseInstallResultSerializer})
    @action(detail=False, methods=[HTTPMethod.POST], url_path="install")
    def install(self, request: Request) -> Response:
        return self._dispatch_install_or_upgrade(request)

    @extend_schema(responses={201: DefenseInstallResultSerializer})
    @action(detail=False, methods=[HTTPMethod.POST], url_path="upgrade")
    def upgrade(self, request: Request) -> Response:
        return self._dispatch_install_or_upgrade(request)

    @extend_schema(responses={200: FundWardResultSerializer})
    @action(detail=False, methods=[HTTPMethod.POST], url_path="fund-ward")
    def fund_ward(self, request: Request) -> Response:
        serializer = FundWardSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = self._resolve_actor(request)
        result = FundRoomWardAction().run(actor=actor, amount=serializer.validated_data["amount"])
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(FundWardResultSerializer(result.data).data, status=status.HTTP_200_OK)
