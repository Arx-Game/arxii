"""ViewSets for player submission endpoints."""

from __future__ import annotations

import builtins
from collections.abc import Iterable
from typing import Any, cast

from django.db.models import Model
from django_filters.rest_framework import DjangoFilterBackend
from evennia.accounts.models import AccountDB
from rest_framework import mixins, serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
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
    IsStaffUser,
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
from world.staff_inbox.services import resolve_identities
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

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Require concrete subclasses to override both hooks. This catches
        # forgotten overrides at import time rather than at the first
        # request that reaches an abstract fallback.
        if cls._get_detail_serializer_class is _BaseSubmissionViewSet._get_detail_serializer_class:
            msg = f"{cls.__name__} must override _get_detail_serializer_class"
            raise NotImplementedError(msg)
        if cls._collect_persona_ids is _BaseSubmissionViewSet._collect_persona_ids:
            msg = f"{cls.__name__} must override _collect_persona_ids"
            raise NotImplementedError(msg)

    def get_permissions(self) -> builtins.list:
        if self.action == "create":
            return [IsAuthenticatedCanSubmit()]
        return [IsStaffUser()]

    def _get_active_persona(self) -> Persona:
        """Resolve the requesting user's active primary persona.

        Uses the unique active character if there is exactly one. If the
        user has multiple active characters, they must specify which
        persona to submit as (future: via a persona_id field). If the
        user has no active character, raises ``ValidationError``.
        """
        user = cast(AccountDB, self.request.user)
        entries = RosterEntry.objects.for_account(user)
        character_ids = list(entries.values_list("character_id", flat=True))

        if not character_ids:
            raise serializers.ValidationError(
                {"detail": "You must be playing a character to submit."},
            )

        personas = list(
            Persona.objects.filter(
                character_id__in=character_ids,
                persona_type=PersonaType.PRIMARY,
            ),
        )

        if not personas:
            raise serializers.ValidationError(
                {"detail": "You must be playing a character to submit."},
            )

        if len(personas) > 1:
            raise serializers.ValidationError(
                {
                    "detail": (
                        "You have multiple active characters. "
                        "Please specify which persona to submit as."
                    ),
                },
            )

        return personas[0]

    def _get_detail_serializer_class(self) -> type[BaseSerializer[Any]]:
        """Subclass hook — return the detail serializer class."""
        msg = "Subclasses must implement _get_detail_serializer_class."
        raise NotImplementedError(msg)

    def _collect_persona_ids(self, rows: Iterable[Model]) -> builtins.list[int]:
        """Collect persona ids referenced by a page of rows.

        Abstract: subclasses must override to declare which persona FKs
        their model carries. ``__init_subclass__`` enforces this.
        """
        msg = "Subclasses must implement _collect_persona_ids."
        raise NotImplementedError(msg)

    def _serializer_context_with_identities(
        self,
        rows: Iterable[Model],
    ) -> dict[str, Any]:
        """Build serializer context with batch-resolved identity data.

        Resolves every persona id referenced by the page in a single
        pair of queries (see ``resolve_identities``) and passes the
        resulting lookup via context so detail serializers can skip the
        per-row ``persona.get_identity_summary()`` walk.
        """
        persona_ids = list({pid for pid in self._collect_persona_ids(rows) if pid})
        identity_lookup = resolve_identities(persona_ids)
        context = self.get_serializer_context()
        context["identity_lookup"] = identity_lookup
        return context

    def list(
        self,
        request: Request,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            context = self._serializer_context_with_identities(page)
            serializer = self.get_serializer(page, many=True, context=context)
            return self.get_paginated_response(serializer.data)
        context = self._serializer_context_with_identities(list(queryset))
        serializer = self.get_serializer(queryset, many=True, context=context)
        return Response(serializer.data)

    def retrieve(
        self,
        request: Request,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        instance = self.get_object()
        context = self._serializer_context_with_identities([instance])
        serializer = self.get_serializer(instance, context=context)
        return Response(serializer.data)

    def perform_create(self, serializer: BaseSerializer[Any]) -> None:
        persona = self._get_active_persona()
        # Auto-populate location from the character's current room.
        # We query ``db_location_id`` via a fresh values_list() lookup
        # to bypass the SharedMemoryModel identity-map cache, which
        # holds a stale Character instance even after
        # ``refresh_from_db``. See
        # ``test_location_picks_up_out_of_band_updates`` for the
        # regression guard — the simpler ``refresh_from_db`` approach
        # fails that test, so this workaround is justified.
        from evennia.objects.models import ObjectDB  # noqa: PLC0415

        location_id = (
            ObjectDB.objects.filter(pk=persona.character_id)
            .values_list("db_location_id", flat=True)
            .first()
        )
        serializer.save(reporter_persona=persona, location_id=location_id)

    def create(
        self,
        request: Request,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        """Override to return the detail serializer shape on create."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        instance = cast(Model, serializer.instance)
        # Batch-resolve identity for the single new row so the detail
        # serializer uses the same context-driven path as list/retrieve.
        context = self._serializer_context_with_identities([instance])
        detail_serializer_class = self._get_detail_serializer_class()
        detail_serializer = detail_serializer_class(
            instance,
            context=context,
        )
        headers = self.get_success_headers(serializer.data)
        return Response(
            detail_serializer.data,
            status=status.HTTP_201_CREATED,
            headers=headers,
        )


class PlayerFeedbackViewSet(_BaseSubmissionViewSet):
    queryset = PlayerFeedback.objects.all().order_by("-created_at")
    filterset_class = PlayerFeedbackFilter

    def get_serializer_class(self) -> type[serializers.Serializer]:
        if self.action == "create":
            return PlayerFeedbackCreateSerializer
        return PlayerFeedbackDetailSerializer

    def _get_detail_serializer_class(self) -> type[BaseSerializer[Any]]:
        return PlayerFeedbackDetailSerializer

    def _collect_persona_ids(self, rows: Iterable[Model]) -> builtins.list[int]:
        return [cast(PlayerFeedback, row).reporter_persona_id for row in rows]


class BugReportViewSet(_BaseSubmissionViewSet):
    queryset = BugReport.objects.all().order_by("-created_at")
    filterset_class = BugReportFilter

    def get_serializer_class(self) -> type[serializers.Serializer]:
        if self.action == "create":
            return BugReportCreateSerializer
        return BugReportDetailSerializer

    def _get_detail_serializer_class(self) -> type[BaseSerializer[Any]]:
        return BugReportDetailSerializer

    def _collect_persona_ids(self, rows: Iterable[Model]) -> builtins.list[int]:
        return [cast(BugReport, row).reporter_persona_id for row in rows]


class PlayerReportViewSet(_BaseSubmissionViewSet):
    queryset = PlayerReport.objects.all().order_by("-created_at")
    filterset_class = PlayerReportFilter

    def get_serializer_class(self) -> type[serializers.Serializer]:
        if self.action == "create":
            return PlayerReportCreateSerializer
        return PlayerReportDetailSerializer

    def _get_detail_serializer_class(self) -> type[BaseSerializer[Any]]:
        return PlayerReportDetailSerializer

    def _collect_persona_ids(self, rows: Iterable[Model]) -> builtins.list[int]:
        ids: set[int] = set()
        for row in rows:
            report = cast(PlayerReport, row)
            ids.add(report.reporter_persona_id)
            ids.add(report.reported_persona_id)
        return list(ids)
