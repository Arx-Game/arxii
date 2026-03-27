from django.db.models import Prefetch, QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from world.events.filters import EventFilter
from world.events.models import Event, EventHost, EventInvitation
from world.events.pagination import EventPagination
from world.events.permissions import IsEventHostOrStaff
from world.events.serializers import (
    EventCreateSerializer,
    EventDetailSerializer,
    EventListSerializer,
)
from world.events.services import (
    cancel_event,
    complete_event,
    create_event,
    schedule_event,
    start_event,
)
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
        return EventDetailSerializer

    def get_queryset(self) -> QuerySet[Event]:
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
            "modification",  # noqa: PREFETCH_STRING — reverse OneToOneField, to_attr not applicable
        )

    def perform_create(self, serializer: EventCreateSerializer) -> None:
        """Create event via service function, deriving host from request user."""
        active_persona = Persona.objects.filter(
            character__roster_entry__tenures__player_data__account=self.request.user,
            character__roster_entry__tenures__end_date__isnull=True,
            persona_type="primary",
        ).first()

        if not active_persona:
            msg = "You must have an active character with a persona to create events."
            raise DRFValidationError(msg)

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
                time_phase=data.get("time_phase", "day"),
            )
        except ValueError as e:
            raise DRFValidationError(str(e)) from e
        serializer.instance = event

    def _refetch_event(self, event: Event) -> Event:
        """Re-fetch event through the queryset to get prefetched data."""
        return self.get_queryset().get(pk=event.pk)

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
