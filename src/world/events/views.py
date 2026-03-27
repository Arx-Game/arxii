from django.db.models import Prefetch, Q, QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from world.events.constants import EventStatus, InvitationTargetType
from world.events.filters import EventFilter
from world.events.models import Event, EventHost, EventInvitation
from world.events.pagination import EventPagination
from world.events.permissions import IsEventHostOrStaff
from world.events.serializers import (
    EventCreateSerializer,
    EventDetailSerializer,
    EventListSerializer,
    EventUpdateSerializer,
)
from world.events.services import (
    cancel_event,
    complete_event,
    create_event,
    schedule_event,
    start_event,
    validate_location_gap,
)
from world.game_clock.constants import TimePhase
from world.scenes.constants import PersonaType
from world.scenes.models import Persona


class EventViewSet(ModelViewSet):
    """ViewSet for listing, creating, and managing events."""

    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_class = EventFilter
    search_fields = ["name", "description"]
    pagination_class = EventPagination

    def get_permissions(self) -> list:
        if self.action in ("list", "retrieve"):
            return [IsAuthenticatedOrReadOnly()]
        if self.action in (
            "update",
            "partial_update",
            "destroy",
            "schedule",
            "start",
            "complete",
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

    def get_queryset(self) -> QuerySet[Event]:
        base_qs = (
            Event.objects.select_related(
                "location__objectdb",
            )
            .prefetch_related(
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
            .order_by("scheduled_real_time")
        )
        return self._apply_visibility_filter(base_qs)

    def _get_active_persona_ids(self) -> list[int]:
        """Get persona IDs for the requesting user's active characters."""
        if not self.request.user.is_authenticated:
            return []
        return list(
            Persona.objects.filter(
                character__roster_entry__tenures__player_data__account=self.request.user,
                character__roster_entry__tenures__end_date__isnull=True,
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
        # TODO: Add org/society membership filtering when membership queries are available

        return qs.filter(public_q | host_q | invited_q).distinct()

    def perform_create(self, serializer: EventCreateSerializer) -> None:
        """Create event via service function, deriving host from request user."""
        persona_ids = self._get_active_persona_ids()
        if not persona_ids:
            msg = "You must have an active character with a persona to create events."
            raise DRFValidationError(msg)
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
        except ValueError as e:
            raise DRFValidationError(str(e)) from e
        serializer.instance = event

    def perform_update(self, serializer: EventUpdateSerializer) -> None:
        """Validate schedule changes and restrict updates to DRAFT/SCHEDULED."""
        event = self.get_object()

        # Only DRAFT/SCHEDULED events can be updated
        if event.status not in (EventStatus.DRAFT, EventStatus.SCHEDULED):
            msg = "Cannot update an event that is active, completed, or cancelled."
            raise DRFValidationError(msg)

        data = serializer.validated_data

        # If scheduled_real_time changed, validate location gap
        new_real_time = data.get("scheduled_real_time")
        if new_real_time and new_real_time != event.scheduled_real_time:
            if not validate_location_gap(
                event.location_id, new_real_time, exclude_event_id=event.id
            ):
                msg = "Another event is scheduled within 6 hours at this location."
                raise DRFValidationError(msg)

        serializer.save()

    def _refetch_event(self, event: Event) -> Event:
        """Re-fetch event with prefetched data, bypassing visibility filters.

        Lifecycle actions (cancel, complete) change status in ways that may
        exclude the event from the visibility-filtered queryset, so we use
        the base queryset with prefetches but without filtering.
        """
        return (
            Event.objects.select_related("location__objectdb")
            .prefetch_related(
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
            .get(pk=event.pk)
        )

    @action(detail=True, methods=["post"])
    def schedule(self, request: Request, pk: int | None = None) -> Response:
        event = self.get_object()
        try:
            schedule_event(event)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(EventDetailSerializer(self._refetch_event(event)).data)

    @action(detail=True, methods=["post"])
    def start(self, request: Request, pk: int | None = None) -> Response:
        event = self.get_object()
        try:
            start_event(event)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(EventDetailSerializer(self._refetch_event(event)).data)

    @action(detail=True, methods=["post"])
    def complete(self, request: Request, pk: int | None = None) -> Response:
        event = self.get_object()
        try:
            complete_event(event)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(EventDetailSerializer(self._refetch_event(event)).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request: Request, pk: int | None = None) -> Response:
        event = self.get_object()
        try:
            cancel_event(event)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(EventDetailSerializer(self._refetch_event(event)).data)
