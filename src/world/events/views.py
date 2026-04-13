from collections.abc import Callable

from django.db import IntegrityError
from django.db.models import Prefetch, Q, QuerySet
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.filters import SearchFilter
from rest_framework.mixins import CreateModelMixin, DestroyModelMixin, ListModelMixin
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet, ModelViewSet

from world.events.constants import EventStatus, InvitationTargetType
from world.events.filters import (
    EventFilter,
    EventInvitationFilter,
    OrganizationSearchFilter,
    SocietySearchFilter,
)
from world.events.models import Event, EventHost, EventInvitation
from world.events.permissions import (
    IsEventHostGMOrStaff,
    IsEventHostOrStaff,
    IsInvitationEventHostOrStaff,
)
from world.events.serializers import (
    EventCreateSerializer,
    EventDetailSerializer,
    EventInvitationSerializer,
    EventInviteSerializer,
    EventListSerializer,
    EventUpdateSerializer,
    OrganizationSearchSerializer,
    SocietySearchSerializer,
)
from world.events.services import (
    cancel_event,
    complete_event,
    create_event,
    invite_organization,
    invite_persona,
    invite_society,
    schedule_event,
    start_event,
    validate_location_gap,
)
from world.events.types import EventError
from world.game_clock.constants import TimePhase
from world.roster.models import RosterEntry
from world.scenes.constants import PersonaType
from world.scenes.models import Persona
from world.societies.models import Organization, Society
from world.stories.pagination import StandardResultsSetPagination


class EventViewSet(ModelViewSet):
    """ViewSet for listing, creating, and managing events."""

    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_class = EventFilter
    search_fields = ["name", "description"]
    pagination_class = StandardResultsSetPagination

    def get_permissions(self) -> list:
        if self.action in ("list", "retrieve"):
            return [IsAuthenticatedOrReadOnly()]
        if self.action == "complete":
            return [IsAuthenticated(), IsEventHostGMOrStaff()]
        if self.action in (
            "update",
            "partial_update",
            "destroy",
            "schedule",
            "start",
            "cancel",
        ):
            return [IsAuthenticated(), IsEventHostOrStaff()]
        return [IsAuthenticated()]

    def get_serializer_class(self):  # type: ignore[override]
        if self.action == "list":
            return EventListSerializer
        if self.action == "create":
            return EventCreateSerializer
        if self.action in ("update", "partial_update"):
            return EventUpdateSerializer
        return EventDetailSerializer

    def _base_queryset(self) -> QuerySet[Event]:
        """Base queryset with all prefetches for event serialization."""
        return Event.objects.select_related(
            "location__objectdb",
        ).prefetch_related(
            Prefetch(
                "hosts",
                queryset=EventHost.objects.select_related("persona"),
                to_attr="hosts_cached",
            ),
            Prefetch(
                "invitations",
                queryset=EventInvitation.objects.select_related(
                    "target_persona",
                    "target_organization",
                    "target_society",
                ),
                to_attr="invitations_cached",
            ),
            "modification",  # noqa: PREFETCH_STRING — reverse OneToOneField
        )

    def get_queryset(self) -> QuerySet[Event]:
        return self._apply_visibility_filter(self._base_queryset().order_by("scheduled_real_time"))

    def _get_active_persona_ids(self) -> list[int]:
        """Get persona IDs for the requesting user's active characters."""
        if not self.request.user.is_authenticated:
            return []
        character_ids = RosterEntry.objects.for_account(self.request.user).values_list(
            "character_sheet_id", flat=True
        )
        return list(
            Persona.objects.filter(
                character_sheet_id__in=character_ids,
                persona_type=PersonaType.PRIMARY,
            ).values_list("id", flat=True)
        )

    def _apply_visibility_filter(self, qs: QuerySet[Event]) -> QuerySet[Event]:
        """Filter queryset to only events visible to the requesting user."""
        # Staff sees everything
        if self.request.user.is_authenticated and self.request.user.is_staff:
            return qs

        qs = qs.exclude(status=EventStatus.CANCELLED)

        if not self.request.user.is_authenticated:
            return qs.filter(is_public=True)

        persona_ids = self._get_active_persona_ids()

        if not persona_ids:
            return qs.filter(is_public=True)

        public_q = Q(is_public=True)
        host_q = Q(hosts__persona_id__in=persona_ids)
        invited_q = Q(
            invitations__target_type=InvitationTargetType.PERSONA,
            invitations__target_persona_id__in=persona_ids,
        )
        org_invited_q = Q(
            invitations__target_type=InvitationTargetType.ORGANIZATION,
            invitations__target_organization__memberships__persona_id__in=persona_ids,
        )
        society_invited_q = Q(
            invitations__target_type=InvitationTargetType.SOCIETY,
            invitations__target_society__organizations__memberships__persona_id__in=persona_ids,
        )

        return qs.filter(
            public_q | host_q | invited_q | org_invited_q | society_invited_q
        ).distinct()

    def perform_create(self, serializer: EventCreateSerializer) -> None:
        """Create event via service function, deriving host from request user."""
        persona_ids = self._get_active_persona_ids()
        if not persona_ids:
            raise DRFValidationError(EventError.NO_PERSONA)
        active_persona = Persona.objects.get(id=persona_ids[0])

        data = serializer.validated_data
        try:
            event = create_event(
                name=data["name"],
                description=data.get("description", ""),
                location_id=data["location"].pk,
                scheduled_real_time=data["scheduled_real_time"],
                host_persona=active_persona,
                is_public=data.get("is_public", True),
                scheduled_ic_time=data.get("scheduled_ic_time"),
                time_phase=data.get("time_phase", TimePhase.DAY),
            )
        except EventError as e:
            raise DRFValidationError(e.user_message) from e
        serializer.instance = event

    def perform_update(self, serializer: EventUpdateSerializer) -> None:
        """Validate schedule changes and restrict updates to DRAFT/SCHEDULED."""
        event = serializer.instance

        # Only DRAFT/SCHEDULED events can be updated
        if event.status not in (EventStatus.DRAFT, EventStatus.SCHEDULED):
            raise DRFValidationError(EventError.UPDATE_LOCKED)

        data = serializer.validated_data

        # If scheduled_real_time changed, validate location gap
        new_real_time = data.get("scheduled_real_time")
        if new_real_time and new_real_time != event.scheduled_real_time:
            if not validate_location_gap(
                event.location_id, new_real_time, exclude_event_id=event.id
            ):
                raise DRFValidationError(EventError.LOCATION_GAP)

        serializer.save()

    def get_serializer_context(self) -> dict:
        context = super().get_serializer_context()
        context["persona_ids"] = set(self._get_active_persona_ids())
        return context

    def _lifecycle_action(self, request: Request, service_fn: Callable[[Event], Event]) -> Response:
        """Execute a lifecycle transition and return the updated event."""
        event = self.get_object()
        try:
            service_fn(event)
        except EventError as e:
            return Response({"detail": e.user_message}, status=status.HTTP_400_BAD_REQUEST)
        context = {"request": request, "persona_ids": set(self._get_active_persona_ids())}
        event.flush_from_cache(force=True)
        return Response(
            EventDetailSerializer(self._base_queryset().get(pk=event.pk), context=context).data
        )

    @action(detail=True, methods=["post"])
    def schedule(self, request: Request, pk: int | None = None) -> Response:
        return self._lifecycle_action(request, schedule_event)

    @action(detail=True, methods=["post"])
    def start(self, request: Request, pk: int | None = None) -> Response:
        return self._lifecycle_action(request, start_event)

    @action(detail=True, methods=["post"])
    def complete(self, request: Request, pk: int | None = None) -> Response:
        return self._lifecycle_action(request, complete_event)

    @action(detail=True, methods=["post"])
    def cancel(self, request: Request, pk: int | None = None) -> Response:
        return self._lifecycle_action(request, cancel_event)


class EventInvitationViewSet(CreateModelMixin, DestroyModelMixin, ListModelMixin, GenericViewSet):
    """ViewSet for managing event invitations."""

    serializer_class = EventInvitationSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = EventInvitationFilter
    pagination_class = StandardResultsSetPagination

    def get_permissions(self) -> list:
        if self.action == "list":
            return [IsAuthenticatedOrReadOnly()]
        return [IsAuthenticated(), IsInvitationEventHostOrStaff()]

    def get_queryset(self) -> QuerySet[EventInvitation]:
        return EventInvitation.objects.select_related(
            "target_persona",
            "target_organization",
            "target_society",
        )

    def get_serializer_class(self):  # type: ignore[override]
        if self.action == "create":
            return EventInviteSerializer
        return EventInvitationSerializer

    def create(self, request: Request, *args: object, **kwargs: object) -> Response:
        """Create an invitation for an event."""
        serializer = EventInviteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        event_id = request.data.get("event")
        event = get_object_or_404(Event, pk=event_id)

        if event.status not in (EventStatus.DRAFT, EventStatus.SCHEDULED):
            return Response(
                {"detail": EventError.INVITE_ACTIVE},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check host permission against the event
        self.check_object_permissions(request, EventInvitation(event=event))

        target_type = serializer.validated_data["target_type"]
        target_id = serializer.validated_data["target_id"]
        invited_by_id = serializer.validated_data.get("invited_by_persona")
        invited_by = get_object_or_404(Persona, pk=invited_by_id) if invited_by_id else None

        target_model = {
            InvitationTargetType.PERSONA: Persona,
            InvitationTargetType.ORGANIZATION: Organization,
            InvitationTargetType.SOCIETY: Society,
        }[target_type]
        target = get_object_or_404(target_model, pk=target_id)

        invite_fn = {
            InvitationTargetType.PERSONA: invite_persona,
            InvitationTargetType.ORGANIZATION: invite_organization,
            InvitationTargetType.SOCIETY: invite_society,
        }[target_type]

        try:
            invitation = invite_fn(event, target, invited_by=invited_by)
        except IntegrityError:
            return Response(
                {"detail": EventError.INVITE_DUPLICATE},
                status=status.HTTP_409_CONFLICT,
            )

        return Response(
            EventInvitationSerializer(invitation).data,
            status=status.HTTP_201_CREATED,
        )

    def perform_destroy(self, instance: EventInvitation) -> None:
        if instance.event.status not in (EventStatus.DRAFT, EventStatus.SCHEDULED):
            raise DRFValidationError(EventError.INVITE_MODIFY_ACTIVE)
        instance.delete()


class OrganizationSearchViewSet(ListModelMixin, GenericViewSet):
    """Search organizations by name for invitation targeting."""

    serializer_class = OrganizationSearchSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = OrganizationSearchFilter
    permission_classes = [IsAuthenticatedOrReadOnly]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self) -> QuerySet[Organization]:
        return Organization.objects.all().order_by("name")


class SocietySearchViewSet(ListModelMixin, GenericViewSet):
    """Search societies by name for invitation targeting."""

    serializer_class = SocietySearchSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = SocietySearchFilter
    permission_classes = [IsAuthenticatedOrReadOnly]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self) -> QuerySet[Society]:
        return Society.objects.all().order_by("name")
