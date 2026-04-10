"""ViewSets for player submission endpoints."""

from __future__ import annotations

from typing import Any, cast

from django_filters.rest_framework import DjangoFilterBackend
from evennia.accounts.models import AccountDB
from rest_framework import mixins, serializers
from rest_framework.serializers import BaseSerializer
from rest_framework.viewsets import GenericViewSet

from world.player_submissions.filters import (
    BugReportFilter,
    PlayerFeedbackFilter,
    PlayerReportFilter,
)
from world.player_submissions.models import BugReport, PlayerFeedback, PlayerReport
from world.player_submissions.permissions import (
    IsAuthenticatedCanSubmit,
    IsStaffForReview,
)
from world.player_submissions.serializers import (
    BugReportCreateSerializer,
    BugReportDetailSerializer,
    PlayerFeedbackCreateSerializer,
    PlayerFeedbackDetailSerializer,
    PlayerReportCreateSerializer,
    PlayerReportDetailSerializer,
)
from world.roster.models import RosterEntry
from world.scenes.constants import PersonaType
from world.scenes.models import Persona
from world.stories.pagination import StandardResultsSetPagination


class _BaseSubmissionViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    GenericViewSet,
):
    """Shared base for submission management ViewSets.

    Create: authenticated players (their own submission).
    List/retrieve/update: staff only (first-PR scope).
    """

    filter_backends = [DjangoFilterBackend]
    pagination_class = StandardResultsSetPagination

    def get_permissions(self) -> list:
        if self.action == "create":
            return [IsAuthenticatedCanSubmit()]
        return [IsStaffForReview()]

    def _get_active_persona(self) -> Persona | None:
        """Resolve the requesting user's active primary persona.

        Returns the primary persona of any character this user is
        currently playing, or None if they have no active character.
        """
        user = cast(AccountDB, self.request.user)
        entries = RosterEntry.objects.for_account(user)
        character_ids = entries.values_list("character_id", flat=True)
        return Persona.objects.filter(
            character_id__in=character_ids,
            persona_type=PersonaType.PRIMARY,
        ).first()


class PlayerFeedbackViewSet(_BaseSubmissionViewSet):
    queryset = PlayerFeedback.objects.all().order_by("-created_at")
    filterset_class = PlayerFeedbackFilter

    def get_serializer_class(self) -> type[serializers.Serializer]:
        if self.action == "create":
            return PlayerFeedbackCreateSerializer
        return PlayerFeedbackDetailSerializer

    def perform_create(self, serializer: BaseSerializer[Any]) -> None:
        persona = self._get_active_persona()
        if persona is None:
            raise serializers.ValidationError(
                {"detail": "You must be playing a character to submit."},
            )
        serializer.save(reporter_persona=persona)


class BugReportViewSet(_BaseSubmissionViewSet):
    queryset = BugReport.objects.all().order_by("-created_at")
    filterset_class = BugReportFilter

    def get_serializer_class(self) -> type[serializers.Serializer]:
        if self.action == "create":
            return BugReportCreateSerializer
        return BugReportDetailSerializer

    def perform_create(self, serializer: BaseSerializer[Any]) -> None:
        persona = self._get_active_persona()
        if persona is None:
            raise serializers.ValidationError(
                {"detail": "You must be playing a character to submit."},
            )
        serializer.save(reporter_persona=persona)


class PlayerReportViewSet(_BaseSubmissionViewSet):
    queryset = PlayerReport.objects.all().order_by("-created_at")
    filterset_class = PlayerReportFilter

    def get_serializer_class(self) -> type[serializers.Serializer]:
        if self.action == "create":
            return PlayerReportCreateSerializer
        return PlayerReportDetailSerializer

    def perform_create(self, serializer: BaseSerializer[Any]) -> None:
        persona = self._get_active_persona()
        if persona is None:
            raise serializers.ValidationError(
                {"detail": "You must be playing a character to submit."},
            )
        serializer.save(reporter_persona=persona)
