"""ViewSets for player submission endpoints."""

from __future__ import annotations

import builtins
from typing import Any

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, serializers
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.viewsets import GenericViewSet

from world.player_submissions.filters import (
    BugReportFilter,
    PlayerFeedbackFilter,
    PlayerReportFilter,
)
from world.player_submissions.models import BugReport, PlayerFeedback, PlayerReport
from world.player_submissions.serializers import (
    BugReportCreateSerializer,
    BugReportDetailSerializer,
    PlayerFeedbackCreateSerializer,
    PlayerFeedbackDetailSerializer,
    PlayerReportCreateSerializer,
    PlayerReportDetailSerializer,
)
from world.stories.pagination import StandardResultsSetPagination


def _resolve_location_id(character_id: int) -> int | None:
    """Look up a character's current room id with a fresh query.

    Bypasses the SharedMemoryModel identity-map cache, which can hold a
    stale Character instance even after ``refresh_from_db``. See
    ``test_location_picks_up_out_of_band_updates`` for the regression
    guard.
    """
    from evennia.objects.models import ObjectDB  # noqa: PLC0415

    return ObjectDB.objects.filter(pk=character_id).values_list("db_location_id", flat=True).first()


class _SubmissionViewSetMixin:
    """Tiny shared config for the three submission ViewSets.

    Just deduplication of permission/context wiring — no abstract
    enforcement, no framework. Each concrete ViewSet still owns its
    queryset, serializers, and filterset.
    """

    filter_backends = [DjangoFilterBackend]
    pagination_class = StandardResultsSetPagination

    def get_permissions(self) -> builtins.list:
        if self.action == "create":
            return [IsAuthenticated()]
        return [IsAdminUser()]

    def get_serializer_context(self) -> dict[str, Any]:
        context = super().get_serializer_context()
        context["account"] = self.request.user
        return context


class PlayerFeedbackViewSet(
    _SubmissionViewSetMixin,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    GenericViewSet,
):
    queryset = PlayerFeedback.objects.select_related(
        "reporter_account",
        "reporter_persona__character_sheet__character",
    ).order_by("-created_at")
    filterset_class = PlayerFeedbackFilter

    def get_serializer_class(self) -> type[serializers.Serializer]:
        if self.action == "create":
            return PlayerFeedbackCreateSerializer
        return PlayerFeedbackDetailSerializer

    def perform_create(self, serializer: serializers.BaseSerializer) -> None:
        persona = serializer.validated_data["reporter_persona"]
        location_id = _resolve_location_id(persona.character_sheet_id)
        serializer.save(
            reporter_account=self.request.user,
            location_id=location_id,
        )


class BugReportViewSet(
    _SubmissionViewSetMixin,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    GenericViewSet,
):
    queryset = BugReport.objects.select_related(
        "reporter_account",
        "reporter_persona__character_sheet__character",
    ).order_by("-created_at")
    filterset_class = BugReportFilter

    def get_serializer_class(self) -> type[serializers.Serializer]:
        if self.action == "create":
            return BugReportCreateSerializer
        return BugReportDetailSerializer

    def perform_create(self, serializer: serializers.BaseSerializer) -> None:
        persona = serializer.validated_data["reporter_persona"]
        location_id = _resolve_location_id(persona.character_sheet_id)
        serializer.save(
            reporter_account=self.request.user,
            location_id=location_id,
        )


class PlayerReportViewSet(
    _SubmissionViewSetMixin,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    GenericViewSet,
):
    queryset = PlayerReport.objects.select_related(
        "reporter_account",
        "reported_account",
        "reporter_persona__character_sheet__character",
        "reported_persona__character_sheet__character",
    ).order_by("-created_at")
    filterset_class = PlayerReportFilter

    def get_serializer_class(self) -> type[serializers.Serializer]:
        if self.action == "create":
            return PlayerReportCreateSerializer
        return PlayerReportDetailSerializer

    def perform_create(self, serializer: serializers.BaseSerializer) -> None:
        persona = serializer.validated_data["reporter_persona"]
        location_id = _resolve_location_id(persona.character_sheet_id)
        serializer.save(
            reporter_account=self.request.user,
            location_id=location_id,
        )
