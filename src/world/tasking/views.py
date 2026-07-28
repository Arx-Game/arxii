"""Tasking board API (#2820 phase 1).

Authoring viewsets (templates, routes) are staff-only. The board viewset
is member-facing: reads scope to orgs the requester's active persona
belongs to; creating a task requires org leadership; assigning an agent
is open to any active member dispatching their own asset (the service
layer re-checks membership and ownership).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from world.tasking.exceptions import TaskingError
from world.tasking.filters import (
    OrgTaskFilterSet,
    TaskOutcomeRouteFilterSet,
    TaskTemplateFilterSet,
)
from world.tasking.models import OrgTask, TaskOutcomeRoute, TaskTemplate
from world.tasking.permissions import IsOrgLeaderForCreate, active_persona_for_request
from world.tasking.serializers import (
    OrgTaskCreateSerializer,
    OrgTaskSerializer,
    TaskAssignSerializer,
    TaskOutcomeRouteSerializer,
    TaskTemplateSerializer,
)
from world.tasking.services import assign_agent, create_task

if TYPE_CHECKING:
    from rest_framework.request import Request


class TaskingPagination(PageNumberPagination):
    page_size = 50


class TaskTemplateViewSet(viewsets.ModelViewSet):
    """Staff authoring CRUD for job templates."""

    queryset = TaskTemplate.objects.all()
    serializer_class = TaskTemplateSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
    pagination_class = TaskingPagination
    filterset_class = TaskTemplateFilterSet


class TaskOutcomeRouteViewSet(viewsets.ModelViewSet):
    """Staff authoring CRUD for per-tier payout routes."""

    queryset = TaskOutcomeRoute.objects.all()
    serializer_class = TaskOutcomeRouteSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
    pagination_class = TaskingPagination
    filterset_class = TaskOutcomeRouteFilterSet


class OrgTaskViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """The org task board: list/inspect/issue/assign."""

    serializer_class = OrgTaskSerializer
    permission_classes = [IsAuthenticated, IsOrgLeaderForCreate]
    pagination_class = TaskingPagination
    filterset_class = OrgTaskFilterSet

    def get_queryset(self):
        persona = active_persona_for_request(self.request)
        if persona is None:
            return OrgTask.objects.none()
        from world.societies.models import OrganizationMembership  # noqa: PLC0415

        member_org_ids = OrganizationMembership.objects.filter(
            persona=persona,
            left_at__isnull=True,
            exiled_at__isnull=True,
        ).values_list("organization_id", flat=True)
        # No Prefetch onto SharedMemoryModel parents (identity-map instances are
        # shared across requests); the list path hands the serializer a
        # fulfillment map via context instead.
        return OrgTask.objects.filter(org_id__in=member_org_ids).select_related(
            "template", "issued_by"
        )

    def list(self, request: Request, *args, **kwargs) -> Response:
        from world.tasking.models import TaskFulfillment  # noqa: PLC0415

        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        rows = page if page is not None else list(queryset)
        active = TaskFulfillment.objects.filter(
            task_id__in=[t.pk for t in rows],
            is_active=True,
        ).select_related("handler", "npc_asset__asset_persona", "resolved_outcome")
        context = {**self.get_serializer_context()}
        context["active_fulfillments_by_task"] = {f.task_id: f for f in active}
        serializer = OrgTaskSerializer(rows, many=True, context=context)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    def create(self, request: Request, *args, **kwargs) -> Response:
        persona = active_persona_for_request(request)
        payload = OrgTaskCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        try:
            task = create_task(
                data["template"],
                data["org"],
                persona,
                target_room=data.get("target_room"),
                target_org=data.get("target_org"),
                target_domain=data.get("target_domain"),
                target_persona=data.get("target_persona"),
            )
        except TaskingError as exc:
            return Response({"detail": exc.user_message}, status=status.HTTP_400_BAD_REQUEST)
        serializer = self.get_serializer(task)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def assign(self, request: Request, pk: str | None = None) -> Response:
        """Dispatch one of the requester's own agents on this task."""
        from world.assets.models import NPCAsset  # noqa: PLC0415

        task = self.get_object()
        persona = active_persona_for_request(request)
        if persona is None:
            return Response(
                {"detail": "No active character."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        payload = TaskAssignSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        npc_asset = NPCAsset.objects.filter(pk=payload.validated_data["npc_asset"]).first()
        if npc_asset is None:
            return Response({"detail": "Unknown agent."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            assign_agent(task, npc_asset, persona)
        except TaskingError as exc:
            return Response({"detail": exc.user_message}, status=status.HTTP_400_BAD_REQUEST)
        task.refresh_from_db()
        return Response(self.get_serializer(task).data, status=status.HTTP_200_OK)
