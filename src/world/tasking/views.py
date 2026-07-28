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

from world.tasking.exceptions import TaskingError
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
        from evennia_extensions.models import RoomProfile  # noqa: PLC0415
        from world.assets.models import NPCAsset  # noqa: PLC0415
        from world.checks.models import CheckType  # noqa: PLC0415
        from world.tasking.listener_services import create_listener_post  # noqa: PLC0415
        from world.tasking.serializers import ListenerPostCreateSerializer  # noqa: PLC0415

        persona = active_persona_for_request(request)
        if persona is None:
            return Response({"detail": "No active character."}, status=status.HTTP_400_BAD_REQUEST)
        payload = ListenerPostCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        npc_asset = NPCAsset.objects.filter(pk=data["npc_asset"]).first()
        room = RoomProfile.objects.filter(pk=data["room"]).first()
        if npc_asset is None or room is None:
            return Response(
                {"detail": "Unknown agent or room."}, status=status.HTTP_400_BAD_REQUEST
            )
        check_type = None
        if data.get("check_type"):
            check_type = CheckType.objects.filter(pk=data["check_type"]).first()
        try:
            post = create_listener_post(
                npc_asset,
                room,
                persona,
                check_type=check_type,
                check_difficulty=data.get("check_difficulty", 0),
            )
        except TaskingError as exc:
            return Response({"detail": exc.user_message}, status=status.HTTP_400_BAD_REQUEST)
        serializer = self.get_serializer(post)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def collect(self, request: Request, pk: str | None = None) -> Response:
        """Collect the oldest pending harvest, in person."""
        from world.tasking.listener_services import collect_harvest  # noqa: PLC0415

        post = self.get_object()
        persona = active_persona_for_request(request)
        if persona is None:
            return Response({"detail": "No active character."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            clue = collect_harvest(post, persona)
        except TaskingError as exc:
            return Response({"detail": exc.user_message}, status=status.HTTP_400_BAD_REQUEST)
        if clue is None:
            detail = "Your agent has little of substance — talk, but nothing solid."
        else:
            detail = f"Your agent leans close: {clue.name}."
        return Response({"detail": detail, "clue": clue.pk if clue else None})


class CounterplayViewSet(viewsets.ViewSet):
    """Spy-vs-spy verbs (#2820 phase 4), all requiring the actor's presence.

    Offensive moves against a PC-run network route through the antagonism
    consent register (``espionage`` category); NPC networks are always-on.
    Suppress/flip find the room's sitting listener themselves — the actor
    doesn't need to know which post id sits there.
    """

    permission_classes = [IsAuthenticated]

    def _room_and_persona(self, request: Request):
        from evennia_extensions.models import RoomProfile  # noqa: PLC0415

        persona = active_persona_for_request(request)
        if persona is None:
            return None, None
        character = persona.character_sheet.character
        room = RoomProfile.objects.filter(pk=character.db_location_id).first()
        return room, persona

    def _sitting_post(self, room):
        from world.tasking.models import ListenerPost  # noqa: PLC0415

        return ListenerPost.objects.filter(
            assignment__room_id=room.pk,
            assignment__is_active=True,
        ).first()

    def _verb(self, request: Request, service) -> Response:
        room, persona = self._room_and_persona(request)
        if room is None:
            return Response({"detail": "No active character."}, status=status.HTTP_400_BAD_REQUEST)
        post = self._sitting_post(room)
        if post is None:
            return Response(
                {"detail": "No one here seems to be listening."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            success = service(persona, post)
        except TaskingError as exc:
            return Response({"detail": exc.user_message}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"success": success})

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["post"])
    def suppress(self, request: Request) -> Response:
        """Intimidate the room's sitting listener into silence."""
        from world.tasking.counterplay_services import suppress_listener  # noqa: PLC0415

        return self._verb(request, suppress_listener)

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["post"])
    def flip(self, request: Request) -> Response:
        """Seduce the room's sitting listener into a double allegiance."""
        from world.tasking.counterplay_services import flip_listener  # noqa: PLC0415

        return self._verb(request, flip_listener)

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["post"])
    def plant(self, request: Request) -> Response:
        """Queue a red herring on a listener you've flipped."""
        from world.character_sheets.models import CharacterSheet  # noqa: PLC0415
        from world.tasking.counterplay_services import plant_red_herring  # noqa: PLC0415
        from world.tasking.models import ListenerPost  # noqa: PLC0415
        from world.tasking.serializers import PlantRedHerringSerializer  # noqa: PLC0415

        persona = active_persona_for_request(request)
        if persona is None:
            return Response({"detail": "No active character."}, status=status.HTTP_400_BAD_REQUEST)
        payload = PlantRedHerringSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        post = ListenerPost.objects.filter(pk=data["post"]).first()
        subject = CharacterSheet.objects.filter(pk=data["subject_sheet"]).first()
        if post is None or subject is None:
            return Response(
                {"detail": "Unknown post or subject."}, status=status.HTTP_400_BAD_REQUEST
            )
        try:
            plant_red_herring(persona, post, subject_sheet=subject, content=data["content"])
        except TaskingError as exc:
            return Response({"detail": exc.user_message}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"success": True})

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["post"])
    def detect(self, request: Request) -> Response:
        """Sweep the current room for informants. Consentless (defensive)."""
        from world.tasking.counterplay_services import detect_listeners  # noqa: PLC0415

        room, persona = self._room_and_persona(request)
        if room is None:
            return Response({"detail": "No active character."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            revealed = detect_listeners(persona, room)
        except TaskingError as exc:
            return Response({"detail": exc.user_message}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"revealed": revealed})

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["post"])
    def clear(self, request: Request) -> Response:
        """Expel listener assignments from a room you hold authority over."""
        from world.tasking.counterplay_services import clear_room_listeners  # noqa: PLC0415

        room, persona = self._room_and_persona(request)
        if room is None:
            return Response({"detail": "No active character."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            count = clear_room_listeners(persona, room)
        except TaskingError as exc:
            return Response({"detail": exc.user_message}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"cleared": count})


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
