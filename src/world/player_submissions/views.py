"""ViewSets for player submission endpoints."""

from __future__ import annotations

import builtins
from http import HTTPMethod
from typing import Any, cast

from django.db.models import QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from evennia.accounts.models import AccountDB
from rest_framework import mixins, serializers, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from world.player_submissions.constants import SubmissionStatus
from world.player_submissions.filters import (
    BugReportFilter,
    PlayerFeedbackFilter,
    PlayerReportFilter,
    SystemErrorReportFilter,
)
from world.player_submissions.github_issues import GitHubIssueError, file_issue_for_report
from world.player_submissions.models import (
    BugReport,
    Petition,
    PlayerFeedback,
    PlayerReport,
    SystemErrorReport,
)
from world.player_submissions.serializers import (
    BugReportCreateSerializer,
    BugReportDetailSerializer,
    FileIssueInputSerializer,
    PetitionCreateSerializer,
    PetitionSerializer,
    PlayerFeedbackCreateSerializer,
    PlayerFeedbackDetailSerializer,
    PlayerReportCreateSerializer,
    PlayerReportDetailSerializer,
    SystemErrorReportDetailSerializer,
)
from world.stories.pagination import StandardResultsSetPagination

# Labels applied to filed issues, per source. Player bugs and captured errors both
# land in the dev bug backlog; the second tag distinguishes their origin.
_BUG_ISSUE_LABELS = ["bug", "player-report"]
_ERROR_ISSUE_LABELS = ["bug", "auto-captured"]


def _issue_payload(report: BugReport | SystemErrorReport) -> dict[str, object]:
    return {
        "github_issue_number": report.github_issue_number,
        "github_issue_url": report.github_issue_url,
    }


def _file_issue(viewset: GenericViewSet, request: Request, *, labels: list[str]) -> Response:
    """Shared body for the staff ``file-issue`` action on both report viewsets.

    Idempotent: a report already linked to an issue returns that issue untouched. The
    staff-edited (already redacted) title + body are filed as-is.
    """
    report = viewset.get_object()
    if report.github_issue_url:
        return Response(_issue_payload(report), status=status.HTTP_200_OK)
    serializer = FileIssueInputSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        file_issue_for_report(
            report,
            title=serializer.validated_data["title"],
            body=serializer.validated_data["body"],
            labels=labels,
        )
    except GitHubIssueError as exc:
        return Response({"detail": exc.user_message}, status=status.HTTP_502_BAD_GATEWAY)
    return Response(_issue_payload(report), status=status.HTTP_201_CREATED)


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

    def perform_update(self, serializer: serializers.BaseSerializer) -> None:
        """Staff resolution stamps the submitter's track record (#2288)."""
        instance = self.get_object()
        old_status = instance.status
        updated = serializer.save()
        if old_status == SubmissionStatus.OPEN and updated.status in (
            SubmissionStatus.REVIEWED,
            SubmissionStatus.DISMISSED,
        ):
            from world.player_submissions.services import record_resolution  # noqa: PLC0415

            record_resolution(updated.reporter_account, updated.status)

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

    @action(detail=True, methods=[HTTPMethod.POST], url_path="file-issue")
    def file_issue(self, request: Request, pk: str | None = None) -> Response:
        """Staff-only: file a public GitHub issue from this bug report (#1164)."""
        return _file_issue(self, request, labels=_BUG_ISSUE_LABELS)


class SystemErrorReportViewSet(
    _SubmissionViewSetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    GenericViewSet,
):
    """Staff triage of auto-captured runtime errors (#1164).

    No create action — the system authors these via ``services.report_error``. Staff list,
    inspect (traceback + occurrence count), and move them OPEN -> REVIEWED / DISMISSED.
    Admin-only on every action (the mixin grants create to authenticated users, but there
    is no create action here, so all actions resolve to IsAdminUser).
    """

    queryset = SystemErrorReport.objects.select_related(
        "actor_persona__character_sheet__character",
    ).order_by("-last_seen")
    filterset_class = SystemErrorReportFilter
    serializer_class = SystemErrorReportDetailSerializer

    @action(detail=True, methods=[HTTPMethod.POST], url_path="file-issue")
    def file_issue(self, request: Request, pk: str | None = None) -> Response:
        """Staff-only: file a public GitHub issue from this captured error (#1164)."""
        return _file_issue(self, request, labels=_ERROR_ISSUE_LABELS)


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


class PetitionViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    GenericViewSet,
):
    """Emergency-only structured petitions (#2288). No free-form queue.

    Players see their own petitions; staff see all (and resolve via the
    ``resolve`` action, which stamps the submitter's track record).
    """

    queryset = Petition.objects.select_related("account", "scene").order_by("-created_at")
    serializer_class = PetitionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ("status", "category")

    def get_queryset(self) -> QuerySet[Petition]:
        qs = super().get_queryset()
        if self.request.user.is_staff:
            return qs
        return qs.filter(account=self.request.user)

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        from world.player_submissions.services import (  # noqa: PLC0415
            StaffContactError,
            submit_petition,
        )

        serializer = PetitionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            petition = submit_petition(
                cast(AccountDB, request.user),
                category=serializer.validated_data["category"],
                description=serializer.validated_data["description"],
                scene=serializer.validated_data.get("scene"),
                subject_character=serializer.validated_data.get("subject_character"),
            )
        except StaffContactError as exc:
            return Response({"detail": exc.user_message}, status=400)
        return Response(self.get_serializer(petition).data, status=201)

    @action(detail=True, methods=[HTTPMethod.POST], permission_classes=[IsAdminUser])
    def resolve(self, request: Request, pk: object = None) -> Response:
        from world.player_submissions.services import (  # noqa: PLC0415
            StaffContactError,
            resolve_petition,
        )

        petition = self.get_object()
        status_value = request.data.get("status", SubmissionStatus.REVIEWED)
        if status_value not in (SubmissionStatus.REVIEWED, SubmissionStatus.DISMISSED):
            return Response({"detail": "Unknown resolution."}, status=400)
        try:
            resolve_petition(
                petition,
                status=status_value,
                staff_notes=str(request.data.get("staff_notes", "")),
            )
        except StaffContactError as exc:
            return Response({"detail": exc.user_message}, status=400)
        return Response(self.get_serializer(petition).data)

    @action(
        detail=True,
        methods=[HTTPMethod.POST],
        url_path="ignore-sender",
        permission_classes=[IsAdminUser],
    )
    def ignore_sender(self, request: Request, pk: object = None) -> Response:
        """Flip the sender's silent perma-ignore bit (#2288). Never disclosed to them."""
        from world.player_submissions.services import sender_context, set_ignored  # noqa: PLC0415

        petition = self.get_object()
        set_ignored(petition.account, ignored=bool(request.data.get("ignored", True)))
        return Response({"sender_context": sender_context(petition.account)})
