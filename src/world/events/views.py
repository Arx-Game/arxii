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

from actions.definitions.events import (
    CancelEventAction,
    CompleteEventAction,
    CreateEventAction,
    InviteToEventAction,
    RespondInvitationAction,
    ScheduleEventAction,
    StartEventAction,
)
from world.events.constants import (
    RSVP_VERB_TO_RESPONSE,
    EventStatus,
    InvitationTargetType,
)
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
from world.events.services import validate_location_gap
from world.events.types import EventError
from world.game_clock.constants import TimePhase
from world.scenes.models import Persona, Scene
from world.societies.models import Organization, Society
from world.stories.pagination import StandardResultsSetPagination


class _EventActorMixin:
    """Resolve the caller's active character ObjectDB for event Actions.

    Shared by ``EventViewSet`` (host actions) and ``EventInvitationViewSet``
    (the invitee ``respond`` action). The host persona is derived from the
    requesting account's active primary personas; its character is the
    ObjectDB handed to the Action as ``actor``.
    """

    request: Request

    def _active_persona_ids(self) -> list[int]:
        """PRIMARY persona IDs for the requesting user's active characters.

        Reads ``user.cached_primary_persona_ids`` — a cached_property on
        the Account typeclass. Evennia's identity map keeps the same
        Account instance in memory across requests, so this list is
        computed once per account per process and reused across requests.
        Invalidation is wired via ``RosterTenure.related_cache_fields``.
        """
        user = self.request.user
        if not user.is_authenticated:
            return []
        return user.cached_primary_persona_ids

    def _actor_or_400(self) -> object:
        """Resolve the caller's active character ObjectDB, or 400 with NO_PERSONA.

        The host persona is derived from the requesting account's active primary
        personas (``_active_persona_ids``); its ``character_sheet.character`` is
        the ObjectDB handed to the Action as ``actor``.
        """
        persona_ids = self._active_persona_ids()
        if not persona_ids:
            raise DRFValidationError(EventError.NO_PERSONA)
        active_persona = Persona.objects.get(id=persona_ids[0])
        try:
            return active_persona.character_sheet.character
        except (AttributeError, active_persona.character_sheet.character.RelatedObjectDoesNotExist):
            raise DRFValidationError(EventError.NO_PERSONA) from None


class EventViewSet(_EventActorMixin, ModelViewSet):
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
            "modification",  # noqa: PREFETCH_STRING
        )

    def get_queryset(self) -> QuerySet[Event]:
        return self._apply_visibility_filter(self._base_queryset().order_by("scheduled_real_time"))

    def _apply_visibility_filter(self, qs: QuerySet[Event]) -> QuerySet[Event]:
        """Filter queryset to only events visible to the requesting user."""
        # Staff sees everything
        if self.request.user.is_authenticated and self.request.user.is_staff:
            return qs

        qs = qs.exclude(status=EventStatus.CANCELLED)

        if not self.request.user.is_authenticated:
            return qs.filter(is_public=True)

        persona_ids = self._active_persona_ids()

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
        """Create an event via ``CreateEventAction`` (ADR-0001 seam)."""
        actor = self._actor_or_400()
        data = serializer.validated_data
        result = CreateEventAction().run(
            actor=actor,
            name=data["name"],
            description=data.get("description", ""),
            location_id=data["location"].pk,
            scheduled_real_time=data["scheduled_real_time"],
            is_public=data.get("is_public", True),
            scheduled_ic_time=data.get("scheduled_ic_time"),
            time_phase=data.get("time_phase", TimePhase.DAY),
        )
        if not result.success:
            raise DRFValidationError(result.message or EventError.NO_PERSONA)
        serializer.instance = Event.objects.get(pk=result.data["event_id"])

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

    def _get_viewer_gm_event_ids(self) -> set[int]:
        """Return the set of event IDs where the requesting user is a scene GM.

        Computed once per request and surfaced via serializer context so
        ``EventDetailSerializer.get_is_gm`` can do an O(1) set membership
        check instead of firing a fresh ``.exists()`` query per row.
        """
        if not self.request.user.is_authenticated:
            return set()
        return set(
            Scene.objects.filter(
                is_active=True,
                participations__account=self.request.user,
                participations__is_gm=True,
            )
            .values_list("event_id", flat=True)
            .distinct()
        )

    def get_serializer_context(self) -> dict:
        context = super().get_serializer_context()
        context["persona_ids"] = set(self._active_persona_ids())
        context["viewer_gm_event_ids"] = self._get_viewer_gm_event_ids()
        return context

    def _lifecycle_action(self, request: Request, action_cls: type) -> Response:
        """Run a host lifecycle transition through its Action and return the event.

        ``get_object()`` enforces the host/GM permission (403 for non-hosts); the
        Action then runs the service and returns a failure message on bad status.
        Lifecycle Actions are account-authorized (a staffer or scene GM can act
        with no character), so the request account — not a resolved actor — is
        passed through ``action.run()``.
        """
        event = self.get_object()
        result = action_cls().run(actor=None, account=request.user, event_id=event.pk)
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        event.flush_from_cache(force=True)
        return Response(
            EventDetailSerializer(
                self._base_queryset().get(pk=event.pk),
                context=self.get_serializer_context(),
            ).data
        )

    @action(detail=True, methods=["post"])
    def schedule(self, request: Request, pk: int | None = None) -> Response:
        return self._lifecycle_action(request, ScheduleEventAction)

    @action(detail=True, methods=["post"])
    def start(self, request: Request, pk: int | None = None) -> Response:
        return self._lifecycle_action(request, StartEventAction)

    @action(detail=True, methods=["post"])
    def complete(self, request: Request, pk: int | None = None) -> Response:
        return self._lifecycle_action(request, CompleteEventAction)

    @action(detail=True, methods=["post"])
    def cancel(self, request: Request, pk: int | None = None) -> Response:
        return self._lifecycle_action(request, CancelEventAction)


class EventInvitationViewSet(
    _EventActorMixin,
    CreateModelMixin,
    DestroyModelMixin,
    ListModelMixin,
    GenericViewSet,
):
    """ViewSet for managing event invitations."""

    serializer_class = EventInvitationSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = EventInvitationFilter
    pagination_class = StandardResultsSetPagination

    def get_permissions(self) -> list:
        if self.action == "list":
            return [IsAuthenticatedOrReadOnly()]
        # ``respond`` is the invitee RSVPing their *own* invitation — the
        # host-permission class does not apply (the invitee is rarely a host);
        # object-level "is this your invite" is enforced inside the Action.
        if self.action == "respond":
            return [IsAuthenticated()]
        return [IsAuthenticated(), IsInvitationEventHostOrStaff()]

    def get_queryset(self) -> QuerySet[EventInvitation]:
        return EventInvitation.objects.select_related(
            "target_persona",
            "target_organization",
            "target_society",
        ).order_by("-pk")

    def get_serializer_class(self):  # type: ignore[override]
        if self.action == "create":
            return EventInviteSerializer
        return EventInvitationSerializer

    def create(self, request: Request, *args: object, **kwargs: object) -> Response:
        """Create an invitation via ``InviteToEventAction`` (ADR-0001 seam)."""
        serializer = EventInviteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        event_id = request.data.get("event")
        event = get_object_or_404(Event, pk=event_id)  # 404 on unknown event

        if event.status not in (EventStatus.DRAFT, EventStatus.SCHEDULED):
            return Response(
                {"detail": EventError.INVITE_ACTIVE},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Host permission against the event (403 for non-hosts).
        self.check_object_permissions(request, EventInvitation(event=event))

        result = InviteToEventAction().run(
            actor=None,
            account=request.user,
            event_id=event.pk,
            target_type=serializer.validated_data["target_type"],
            target_id=serializer.validated_data["target_id"],
            invited_by_persona_id=serializer.validated_data.get("invited_by_persona"),
        )
        if not result.success:
            # Duplicate-target surfaces as 409 (mirrors the prior IntegrityError path);
            # any other failure (bad target type) is a 400.
            code = (
                status.HTTP_409_CONFLICT
                if result.message == EventError.INVITE_DUPLICATE
                else status.HTTP_400_BAD_REQUEST
            )
            return Response({"detail": result.message}, status=code)

        invitation = EventInvitation.objects.select_related(
            "target_persona", "target_organization", "target_society"
        ).get(pk=result.data["invitation_id"])
        return Response(
            EventInvitationSerializer(invitation).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def respond(self, request: Request, pk: int | None = None) -> Response:
        """An invitee RSVPs accept/decline to their own persona invitation.

        The invitee (not the host) is the actor here; object-level "is this your
        invitation" is enforced inside the Action (the persona must be the
        invitation's ``target_persona``), so the permission class only checks
        authentication.
        """
        response_str = request.data.get("response", "").strip().lower()
        if response_str not in RSVP_VERB_TO_RESPONSE:
            return Response(
                {"detail": "response must be 'accept' or 'decline'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        actor = self._actor_or_400()
        result = RespondInvitationAction().run(
            actor=actor,
            invitation_id=pk,
            response=RSVP_VERB_TO_RESPONSE[response_str],
        )
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"success": True, "message": result.message}, status=status.HTTP_200_OK)

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
