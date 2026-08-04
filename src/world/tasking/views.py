"""Tasking board API (#2820 phase 1).

Authoring viewsets (templates, routes) are staff-only. The board viewset
is member-facing: reads scope to orgs the requester's active persona
belongs to; creating a task requires org leadership; assigning an agent
is open to any active member dispatching their own asset (the service
layer re-checks membership and ownership).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from world.tasking.filters import (
    OrgRosterFilterSet,
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

if TYPE_CHECKING:
    from rest_framework.request import Request


_NO_ACTIVE_CHARACTER = "No active character."


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


class OrgRosterViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """The org's held agents (#2820 phase 2) — the board's Roster panel.

    Visibility mirrors the task board: active members plus parent-org
    oversight. Non-members simply see an empty list; the ``org`` filter
    narrows within the allowed set.
    """

    permission_classes = [IsAuthenticated]
    pagination_class = TaskingPagination
    filterset_class = OrgRosterFilterSet

    def get_serializer_class(self):
        from world.assets.serializers import NPCAssetSerializer  # noqa: PLC0415

        return NPCAssetSerializer

    def get_queryset(self):
        from world.assets.models import NPCAsset  # noqa: PLC0415
        from world.societies.models import OrganizationMembership  # noqa: PLC0415
        from world.societies.office_services import overseen_org_ids  # noqa: PLC0415

        persona = active_persona_for_request(self.request)
        if persona is None:
            return NPCAsset.objects.none()
        member_org_ids = list(
            OrganizationMembership.objects.filter(
                persona=persona,
                left_at__isnull=True,
                exiled_at__isnull=True,
            ).values_list("organization_id", flat=True)
        )
        allowed = set(member_org_ids) | set(overseen_org_ids(persona))
        return NPCAsset.objects.filter(promoter_org_id__in=allowed).select_related("asset_persona")


class ListenerPostViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Standing listener posts (#2820 phase 3) — the board's Postings panel.

    Visibility: your own posts (handler), plus posts whose agent is held by
    an org you belong to or oversee. ``collect`` requires the handler's body
    in the posted room — the visit is the exposure surface.
    """

    permission_classes = [IsAuthenticated]
    pagination_class = TaskingPagination

    def get_serializer_class(self):
        from world.tasking.serializers import ListenerPostSerializer  # noqa: PLC0415

        return ListenerPostSerializer

    def get_queryset(self):
        from django.db.models import Q  # noqa: PLC0415

        from world.societies.models import OrganizationMembership  # noqa: PLC0415
        from world.societies.office_services import overseen_org_ids  # noqa: PLC0415
        from world.tasking.models import ListenerPost  # noqa: PLC0415

        persona = active_persona_for_request(self.request)
        if persona is None:
            return ListenerPost.objects.none()
        member_org_ids = list(
            OrganizationMembership.objects.filter(
                persona=persona,
                left_at__isnull=True,
                exiled_at__isnull=True,
            ).values_list("organization_id", flat=True)
        )
        allowed = set(member_org_ids) | set(overseen_org_ids(persona))
        visible = Q(handler=persona) | Q(assignment__npc_asset__promoter_org_id__in=allowed)
        return (
            ListenerPost.objects.filter(visible, assignment__is_active=True)
            .select_related("assignment", "assignment__npc_asset", "handler")
            .distinct()
        )

    def create(self, request: Request, *args, **kwargs) -> Response:
        """Post a listener — through PostListenerAction (ADR-0001)."""
        from actions.registry import get_action  # noqa: PLC0415
        from world.tasking.models import ListenerPost  # noqa: PLC0415
        from world.tasking.serializers import ListenerPostCreateSerializer  # noqa: PLC0415

        persona = active_persona_for_request(request)
        if persona is None:
            return Response({"detail": _NO_ACTIVE_CHARACTER}, status=status.HTTP_400_BAD_REQUEST)
        payload = ListenerPostCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        result = get_action("post_listener").run(
            persona.character_sheet.character,
            npc_asset_id=data["npc_asset"],
            room_id=data["room"],
            check_type_id=data.get("check_type"),
            check_difficulty=data.get("check_difficulty", 0),
        )
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        post = ListenerPost.objects.get(pk=result.data["post_id"])
        serializer = self.get_serializer(post)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def collect(self, request: Request, pk: str | None = None) -> Response:
        """Collect in person — through CollectHarvestAction (ADR-0001)."""
        from actions.registry import get_action  # noqa: PLC0415

        post = self.get_object()
        persona = active_persona_for_request(request)
        if persona is None:
            return Response({"detail": _NO_ACTIVE_CHARACTER}, status=status.HTTP_400_BAD_REQUEST)
        result = get_action("collect_harvest").run(
            persona.character_sheet.character, post_id=post.pk
        )
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": result.message})


class CounterplayViewSet(viewsets.ViewSet):
    """Spy-vs-spy verbs (#2820 phase 4), all requiring the actor's presence.

    Offensive moves against a PC-run network route through the antagonism
    consent register (``espionage`` category); NPC networks are always-on.
    Suppress/flip find the room's sitting listener themselves — the actor
    doesn't need to know which post id sits there.
    """

    permission_classes = [IsAuthenticated]

    def _dispatch(self, request: Request, action_key: str, **kwargs) -> Response:
        """Run a counterplay action as the requester's character (ADR-0001)."""
        from actions.registry import get_action  # noqa: PLC0415

        persona = active_persona_for_request(request)
        if persona is None:
            return Response({"detail": _NO_ACTIVE_CHARACTER}, status=status.HTTP_400_BAD_REQUEST)
        result = get_action(action_key).run(persona.character_sheet.character, **kwargs)
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": result.message, **(result.data or {})})

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["post"])
    def suppress(self, request: Request) -> Response:
        """Intimidate the room's sitting listener into silence."""
        return self._dispatch(request, "suppress_listener")

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["post"])
    def flip(self, request: Request) -> Response:
        """Seduce the room's sitting listener into a double allegiance."""
        return self._dispatch(request, "flip_listener")

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["post"])
    def plant(self, request: Request) -> Response:
        """Queue a red herring on a listener you've flipped."""
        from world.tasking.serializers import PlantRedHerringSerializer  # noqa: PLC0415

        payload = PlantRedHerringSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        return self._dispatch(
            request,
            "plant_red_herring",
            post_id=data["post"],
            subject_sheet_id=data["subject_sheet"],
            content=data["content"],
        )

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["post"])
    def detect(self, request: Request) -> Response:
        """Sweep the current room for informants. Consentless (defensive)."""
        return self._dispatch(request, "detect_listeners")

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["post"])
    def clear(self, request: Request) -> Response:
        """Expel listener assignments from a room you hold authority over."""
        return self._dispatch(request, "clear_room_listeners")


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
        from django.db.models import Q  # noqa: PLC0415

        from world.societies.models import OrganizationMembership  # noqa: PLC0415
        from world.societies.office_services import overseen_org_ids  # noqa: PLC0415

        member_org_ids = OrganizationMembership.objects.filter(
            persona=persona,
            left_at__isnull=True,
            exiled_at__isnull=True,
        ).values_list("organization_id", flat=True)
        # Membership grants the board; parent-org oversight (#2820 phase 2 —
        # parent leadership + spymaster office) grants read on child boards.
        visible = Q(org_id__in=member_org_ids) | Q(org_id__in=overseen_org_ids(persona))
        # No Prefetch onto SharedMemoryModel parents (identity-map instances are
        # shared across requests); the list path hands the serializer a
        # fulfillment map via context instead.
        return OrgTask.objects.filter(visible).select_related("template", "issued_by")

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
        """Issue a task — dispatched through IssueOrgTaskAction (ADR-0001)."""
        from actions.registry import get_action  # noqa: PLC0415

        persona = active_persona_for_request(request)
        payload = OrgTaskCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        result = get_action("issue_org_task").run(
            persona.character_sheet.character,
            template_id=data["template"].pk,
            org_id=data["org"].pk,
            target_room_id=data.get("target_room").pk if data.get("target_room") else None,
            target_org_id=data.get("target_org").pk if data.get("target_org") else None,
            target_domain_id=data.get("target_domain").pk if data.get("target_domain") else None,
            target_persona_id=(
                data.get("target_persona").pk if data.get("target_persona") else None
            ),
            target_crisis_id=(data.get("target_crisis").pk if data.get("target_crisis") else None),
        )
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        task = OrgTask.objects.get(pk=result.data["task_id"])
        serializer = self.get_serializer(task)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def accept(self, request: Request, pk: str | None = None) -> Response:
        """Pick this task up yourself as a mission (#2820 phase 5)."""

        from actions.registry import get_action  # noqa: PLC0415

        task = self.get_object()
        persona = active_persona_for_request(request)
        if persona is None:
            return Response({"detail": _NO_ACTIVE_CHARACTER}, status=status.HTTP_400_BAD_REQUEST)
        result = get_action("accept_org_task").run(
            persona.character_sheet.character, task_id=task.pk
        )
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        task.refresh_from_db()
        data = self.get_serializer(task).data
        data["mission_instance"] = result.data["mission_instance_id"]
        return Response(data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def assign(self, request: Request, pk: str | None = None) -> Response:
        """Dispatch an agent — through AssignTaskAgentAction (ADR-0001)."""
        from actions.registry import get_action  # noqa: PLC0415

        task = self.get_object()
        persona = active_persona_for_request(request)
        if persona is None:
            return Response(
                {"detail": _NO_ACTIVE_CHARACTER},
                status=status.HTTP_400_BAD_REQUEST,
            )
        payload = TaskAssignSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        result = get_action("assign_task_agent").run(
            persona.character_sheet.character,
            task_id=task.pk,
            npc_asset_id=payload.validated_data["npc_asset"],
        )
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        task.refresh_from_db()
        return Response(self.get_serializer(task).data, status=status.HTTP_200_OK)
