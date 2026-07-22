"""DRF viewsets for the unified NPC service framework.

Two surfaces:

1. Staff-only CRUD viewsets over `NPCRole`, `NPCServiceOffer`,
   `NPCStanding`, `OfferCooldown`, per-kind details models.
2. Player-facing `InteractionViewSet` — start/resolve/end actions that
   dispatch through ``actions.definitions.npc_services`` and keep the
   ephemeral interaction state in `request.session`.
"""

from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from actions.definitions.npc_services import (
    end_npc_interaction,
    resolve_npc_offer,
    start_npc_interaction,
)
from world.gm.permissions import IsGMOrStaff
from world.npc_services.filters import (
    MissionOfferDetailsFilterSet,
    NPCRoleFilterSet,
    NPCServiceOfferFilterSet,
    NPCStandingFilterSet,
    OfferCooldownFilterSet,
    PermitOfferDetailsFilterSet,
    RecordedProfileFilterSet,
)
from world.npc_services.models import (
    MissionOfferDetails,
    NPCRole,
    NPCServiceOffer,
    NPCStanding,
    OfferCooldown,
    OfferSummons,
    PermitOfferDetails,
    RecordedProfile,
)
from world.npc_services.serializers import (
    InteractionResolveRequestSerializer,
    InteractionStartRequestSerializer,
    InteractionStateSerializer,
    MissionOfferDetailsSerializer,
    NPCRoleSerializer,
    NPCServiceOfferSerializer,
    NPCStandingSerializer,
    OfferCooldownSerializer,
    OfferSummonsCreateSerializer,
    OfferSummonsSerializer,
    PermitOfferDetailsSerializer,
    RecordedProfileCompleteSerializer,
    RecordedProfileSerializer,
    SummonsRespondSerializer,
)
from world.npc_services.services import (
    InteractionSession,
    RecordedProfileError,
    complete_recorded_profile,
    serialize_npc_session_state,
)
from world.scenes.models import Persona

# Key under which the in-flight interaction state lives in request.session.
# One active interaction per Django session; start while one exists raises
# 409 Conflict (the player has to end the prior one first).
_SESSION_KEY = "npc_interaction"


class NPCServicesPagination(PageNumberPagination):
    """Shared pagination for the NPC services authoring API."""

    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


class NPCStandingViewSet(viewsets.ModelViewSet):
    """Staff CRUD for per-(PC persona, NPC persona) standing rows."""

    queryset = NPCStanding.objects.all().order_by("pk")
    serializer_class = NPCStandingSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
    pagination_class = NPCServicesPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = NPCStandingFilterSet


class NPCRoleViewSet(viewsets.ModelViewSet):
    """Staff CRUD for NPC roles (the kind-of-NPC bundle for offers)."""

    queryset = NPCRole.objects.all().order_by("pk")
    serializer_class = NPCRoleSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
    pagination_class = NPCServicesPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = NPCRoleFilterSet


class NPCServiceOfferViewSet(viewsets.ModelViewSet):
    """Staff CRUD for offers (gated services on an NPC role)."""

    queryset = NPCServiceOffer.objects.all().order_by("pk")
    serializer_class = NPCServiceOfferSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
    pagination_class = NPCServicesPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = NPCServiceOfferFilterSet


class OfferCooldownViewSet(viewsets.ModelViewSet):
    """Staff CRUD for per-(offer, persona) cooldown rows."""

    queryset = OfferCooldown.objects.all().order_by("pk")
    serializer_class = OfferCooldownSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
    pagination_class = NPCServicesPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = OfferCooldownFilterSet


class PermitOfferDetailsViewSet(viewsets.ModelViewSet):
    """Staff CRUD for permit offer details (1:1 to an NPCServiceOffer)."""

    queryset = PermitOfferDetails.objects.all().order_by("pk")
    serializer_class = PermitOfferDetailsSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
    pagination_class = NPCServicesPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = PermitOfferDetailsFilterSet


class MissionOfferDetailsViewSet(viewsets.ModelViewSet):
    """Staff CRUD for mission-kind offer details (1:1 to an NPCServiceOffer).

    Parallels ``PermitOfferDetailsViewSet`` (Plan 3 #668) and unblocks the
    npc-services Mission Studio editor (#728). ``role`` on the model is
    denormalized from ``offer.role`` via the model's ``save()`` override
    (per #686 Phase 6), so the serializer marks it read-only — the FE
    sets `offer` and the catalog uniqueness `(role, mission_template)`
    is enforced at the DB level via the auto-mirrored FK.
    """

    queryset = MissionOfferDetails.objects.all().order_by("pk")
    serializer_class = MissionOfferDetailsSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
    pagination_class = NPCServicesPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = MissionOfferDetailsFilterSet


# ---------------------------------------------------------------------------
# Player-facing interaction state machine.
#
# Three actions — start, resolve, end. State lives in request.session
# (one active interaction per session). The viewset rehydrates an
# InteractionSession from the stored dict on each call, mutates it, and
# writes the updated state back. End closes the session and clears the
# session key.
# ---------------------------------------------------------------------------


def _stash(request: Request, session: InteractionSession) -> None:
    """Persist the small state slice we need to rehydrate this session."""
    request.session[_SESSION_KEY] = {
        "role_id": session.role.pk,
        "persona_id": session.persona.pk,
        "npc_persona_id": session.npc_persona.pk if session.npc_persona else None,
        "character_id": session.character.pk,
        "current_rapport": session.current_rapport,
    }


def _rehydrate(request: Request) -> InteractionSession:
    """Rebuild an InteractionSession from request.session state.

    Raises 404 if no interaction is in flight.
    """
    state = request.session.get(_SESSION_KEY)
    if state is None:
        msg = "No interaction in progress for this session."
        raise NotFound(msg)
    role = NPCRole.objects.filter(pk=state["role_id"]).first()
    persona = Persona.objects.filter(pk=state["persona_id"]).first()
    npc_persona = (
        Persona.objects.filter(pk=state["npc_persona_id"]).first()
        if state.get("npc_persona_id")
        else None
    )
    from evennia.objects.models import ObjectDB  # noqa: PLC0415

    character = ObjectDB.objects.filter(pk=state["character_id"]).first()
    if role is None or persona is None or character is None:
        # Stored IDs no longer resolve — treat as if the interaction ended.
        del request.session[_SESSION_KEY]
        msg = "Interaction session is stale (referenced row removed)."
        raise NotFound(msg)
    return InteractionSession(
        role=role,
        persona=persona,
        npc_persona=npc_persona,
        character=character,
        current_rapport=state["current_rapport"],
    )


class InteractionViewSet(viewsets.ViewSet):
    """Player-facing endpoints driving the NPC-service interaction state machine.

    One active interaction per Django session — calling ``start`` while a
    session is in-flight returns 409. ``resolve`` and ``end`` operate on
    the current in-flight session; both return 404 if none exists.

    The viewset is a thin wrapper over the registry Actions in
    ``actions.definitions.npc_services``; each endpoint delegates to
    ``action.run(actor=character)`` and manages the small session slice
    stored in ``request.session``.
    """

    permission_classes = [IsAuthenticated]

    def _puppet_character(self, request: Request):
        """Return the user's currently-puppeted Character ObjectDB.

        DRF's ``request.user`` is the AccountDB; the ``puppet`` property
        on the typeclass returns the live puppet (or None when no
        Session has puppeted anything). A missing attribute means
        "no puppet" and is surfaced as 400.
        """
        puppet = request.user.puppet if hasattr(request.user, "puppet") else None
        if puppet is None:
            msg = (
                "No puppeted character — log in and assume a character before "
                "starting an NPC interaction."
            )
            raise ValidationError(msg)
        return puppet

    @extend_schema(
        request=InteractionStartRequestSerializer,
        responses={
            201: InteractionStateSerializer,
            400: OpenApiResponse(description="No puppeted character or no role was provided."),
            404: OpenApiResponse(description="NPC role or persona was not found."),
            409: OpenApiResponse(description="An interaction is already in flight."),
            500: OpenApiResponse(
                description="Character sheet invariant breach (missing primary persona)."
            ),
        },
    )
    @action(detail=False, methods=["post"])
    def start(self, request: Request) -> Response:
        if _SESSION_KEY in request.session:
            return Response(
                {"detail": "An interaction is already in flight; end it first."},
                status=status.HTTP_409_CONFLICT,
            )
        body = InteractionStartRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        character = self._puppet_character(request)

        result = start_npc_interaction.run(
            actor=character,
            role_id=body.validated_data["role_id"],
            npc_persona_id=body.validated_data.get("npc_persona_id"),
        )
        if not result.success:
            if result.data.get("invariant_breach"):
                return Response(
                    {"detail": result.message or "Character sheet invariant breach."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
            raise NotFound(result.message)
        session = result.data["session"]
        _stash(request, session)
        return Response(serialize_npc_session_state(session), status=status.HTTP_201_CREATED)

    @extend_schema(
        request=InteractionResolveRequestSerializer,
        responses={
            200: InteractionStateSerializer,
            400: OpenApiResponse(
                description=(
                    "No puppeted character, no offer, offer not eligible, "
                    "or the interaction has already ended."
                )
            ),
            404: OpenApiResponse(description="No interaction in progress or offer not found."),
        },
    )
    @action(detail=False, methods=["post"])
    def resolve(self, request: Request) -> Response:
        body = InteractionResolveRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        session = _rehydrate(request)
        character = self._puppet_character(request)

        result = resolve_npc_offer.run(
            actor=character,
            session=session,
            offer_id=body.validated_data["offer_id"],
            acknowledge_risk=body.validated_data["acknowledge_risk"],
        )
        if not result.success:
            if result.data.get("not_found"):
                raise NotFound(result.message)
            raise ValidationError(result.message)

        if result.data["session"].closed:
            request.session.pop(_SESSION_KEY, None)
        else:
            _stash(request, result.data["session"])
        return Response(
            serialize_npc_session_state(
                result.data["session"],
                last_result_message=result.data.get("last_result_message", ""),
            ),
        )

    @extend_schema(
        responses={
            200: InteractionStateSerializer,
            400: OpenApiResponse(description="No puppeted character."),
            404: OpenApiResponse(description="No interaction in progress."),
        },
    )
    @action(detail=False, methods=["post"])
    def end(self, request: Request) -> Response:
        session = _rehydrate(request)
        character = self._puppet_character(request)

        result = end_npc_interaction.run(actor=character, session=session)
        if not result.success:
            raise NotFound(result.message)

        request.session.pop(_SESSION_KEY, None)
        return Response(serialize_npc_session_state(result.data["session"]))


class OfferSummonsViewSet(viewsets.ModelViewSet):
    """Directed-offer summonses (#2050).

    - GM/staff: create + list all summonses.
    - Players: list summonses directed at their active persona; respond via
      the ``respond`` action.
    """

    serializer_class = OfferSummonsSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = NPCServicesPagination
    queryset = OfferSummons.objects.select_related("offer__role", "target_persona").all()

    def get_queryset(self) -> object:
        """Staff sees all; players see only summonses directed at their persona."""
        qs = self.queryset
        user = self.request.user
        if user.is_staff:
            return qs
        # GMs see all (they create and manage summonses).
        if user.gm_profile_or_none is not None:
            return qs
        # Non-staff: scope to the caller's puppeted sheet via the canonical
        # resolver (handles AnonymousUser and truthy non-character puppets).
        from world.roster.selectors import puppeted_sheet_for  # noqa: PLC0415

        sheet_data = puppeted_sheet_for(user)
        if sheet_data is None:
            return qs.none()
        # Private self-view: summonses addressed to any of the caller's
        # personas, so one sent to the primary still lists while the player
        # presents as an alt. No persona resolution, no cross-persona leak —
        # every face here belongs to the same sheet.
        return qs.filter(target_persona__character_sheet=sheet_data)

    def get_permissions(self) -> list:
        """Create is GM/staff only; list/retrieve/respond are open to authenticated users."""
        if self.action in ("create", "destroy", "update", "partial_update"):
            return [IsAuthenticated(), IsGMOrStaff()]
        return super().get_permissions()

    @extend_schema(
        request=OfferSummonsCreateSerializer,
        responses={
            201: OfferSummonsSerializer,
            400: OpenApiResponse(description="Validation error."),
            403: OpenApiResponse(description="Not a GM or staff."),
        },
    )
    def create(self, request: Request, *args: object, **kwargs: object) -> Response:
        from world.npc_services.summons import create_summons  # noqa: PLC0415

        body = OfferSummonsCreateSerializer(data=request.data)
        body.is_valid(raise_exception=True)

        gm_profile = request.user.gm_profile_or_none
        summons = create_summons(
            body.offer,
            body.target_persona,
            message=body.validated_data.get("message", ""),
            expires_at=body.validated_data.get("expires_at"),
            created_by=gm_profile,
        )

        serializer = OfferSummonsSerializer(summons)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        request=SummonsRespondSerializer,
        responses={
            200: OpenApiResponse(description="Summons responded to."),
            400: OpenApiResponse(
                description="Summons is not pending or risk acknowledgement required."
            ),
            404: OpenApiResponse(description="Summons not found."),
        },
    )
    @action(detail=True, methods=["post"])
    def respond(self, request: Request, pk: int | str | None = None) -> Response:
        from world.npc_services.summons import respond_to_summons  # noqa: PLC0415

        summons = OfferSummons.objects.filter(pk=pk).first()
        if summons is None:
            msg = "That summons was not found."
            raise NotFound(msg)

        body = SummonsRespondSerializer(data=request.data)
        body.is_valid(raise_exception=True)

        puppet = request.user.puppet
        if puppet is None:
            msg = "No puppeted character — log in and assume a character."
            raise ValidationError(msg)

        result = respond_to_summons(
            summons,
            puppet,
            accept=body.validated_data["accept"],
            acknowledge_risk=body.validated_data["acknowledge_risk"],
        )

        data: dict = {
            "success": result.success,
            "message": result.message,
        }
        if result.risk_tier is not None:
            data["risk_tier"] = result.risk_tier
            data["stake_summaries"] = list(result.stake_summaries)
            data["requires_risk_acknowledgement"] = True
        if result.instance_pk is not None:
            data["instance_pk"] = result.instance_pk
        return Response(data)


class RecordedProfileViewSet(viewsets.ReadOnlyModelViewSet):
    """A player's Archive profile sittings (#2632).

    Lists the caller's own personas' recorded profiles (COMMISSIONED sittings
    + the permanent RECORDED archive). ``complete`` finalizes a COMMISSIONED
    sitting with the write-up text — it becomes the character's current
    description and archives forever. Public in-world Archive browsing is a
    future surface; this endpoint is owner-scoped.
    """

    queryset = RecordedProfile.objects.select_related("persona", "era").order_by("-created_at")
    serializer_class = RecordedProfileSerializer
    filterset_class = RecordedProfileFilterSet
    filter_backends = [DjangoFilterBackend]
    pagination_class = NPCServicesPagination
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_staff:
            return qs
        return qs.filter(persona__character_sheet__character__db_account=user)

    @extend_schema(
        request=RecordedProfileCompleteSerializer,
        responses={200: RecordedProfileSerializer},
    )
    @action(detail=True, methods=["post"])
    def complete(self, request: Request, pk: str | None = None) -> Response:
        """Finalize a commissioned sitting with the player-written profile text."""
        profile = self.get_object()
        input_serializer = RecordedProfileCompleteSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        try:
            profile = complete_recorded_profile(profile, input_serializer.validated_data["text"])
        except RecordedProfileError as exc:
            raise ValidationError(exc.user_message) from exc
        return Response(RecordedProfileSerializer(profile).data)
