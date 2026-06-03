"""DRF viewsets for the unified NPC service framework.

Two surfaces:

1. Staff-only CRUD viewsets over `NPCRole`, `NPCServiceOffer`,
   `NPCStanding`, `OfferCooldown`, per-kind details models.
2. Player-facing `InteractionViewSet` — start/resolve/end actions that
   drive the in-memory interaction state machine in `services.py`.
   State lives in `request.session` for the lifetime of one interaction
   per session.
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

from world.npc_services.filters import (
    NPCRoleFilterSet,
    NPCServiceOfferFilterSet,
    NPCStandingFilterSet,
    OfferCooldownFilterSet,
)
from world.npc_services.models import (
    NPCRole,
    NPCServiceOffer,
    NPCStanding,
    OfferCooldown,
    PermitOfferDetails,
)
from world.npc_services.serializers import (
    InteractionOfferSerializer,
    InteractionResolveRequestSerializer,
    InteractionStartRequestSerializer,
    InteractionStateSerializer,
    NPCRoleSerializer,
    NPCServiceOfferSerializer,
    NPCStandingSerializer,
    OfferCooldownSerializer,
    PermitOfferDetailsSerializer,
)
from world.npc_services.services import (
    InteractionSession,
    ResolveOfferError,
    available_offers,
    end_interaction,
    persona_for_character,
    resolve_offer,
    start_interaction,
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


# ---------------------------------------------------------------------------
# Player-facing interaction state machine.
#
# Three actions — start, resolve, end. State lives in request.session
# (one active interaction per session). The viewset rehydrates an
# InteractionSession from the stored dict on each call, mutates it, and
# writes the updated state back. End closes the session and clears the
# session key.
# ---------------------------------------------------------------------------


def _serialize_state(
    session: InteractionSession,
    *,
    last_result_message: str = "",
) -> dict:
    """Compose the response payload from a (live or freshly-closed) session."""
    offers = available_offers(session) if not session.closed else []
    serialized_offers = InteractionOfferSerializer(
        [
            {
                "id": o.pk,
                "label": o.label,
                "kind": o.kind,
                "is_final": o.is_final,
                "rapport_requirement": o.rapport_requirement,
            }
            for o in offers
        ],
        many=True,
    ).data
    return InteractionStateSerializer(
        {
            "role_id": session.role.pk,
            "current_rapport": session.current_rapport,
            "closed": session.closed,
            "available_offers": serialized_offers,
            "last_result_message": last_result_message,
        }
    ).data


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
    """Player-facing endpoints driving the in-memory interaction state machine.

    One active interaction per Django session — calling ``start`` while a
    session is in-flight returns 409. ``resolve`` and ``end`` operate on
    the current in-flight session; both return 404 if none exists.

    The PC's persona is resolved from the request user's puppeted
    character via :func:`persona_for_character` (raises loud on missing
    sheet per the CLAUDE.md invariant — surfaces as 400).
    """

    permission_classes = [IsAuthenticated]

    def _puppet_character(self, request: Request):
        """Return the user's currently-puppeted Character ObjectDB.

        DRF's ``request.user`` is the AccountDB; the ``puppet`` property
        on the typeclass returns the live puppet (or None when no
        Session has puppeted anything). We swallow any access-time
        exception (test scaffolding can hit an AccountDB without typeclass
        machinery loaded) and treat it as "no puppet" — surfaced as 400.
        """
        try:
            puppet = request.user.puppet
        except (AttributeError, Exception):  # noqa: BLE001
            puppet = None
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
            409: OpenApiResponse(description="An interaction is already in flight."),
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
        role_id = body.validated_data["role_id"]
        role = NPCRole.objects.filter(pk=role_id).first()
        if role is None:
            msg = f"NPCRole {role_id} not found."
            raise NotFound(msg)
        npc_persona = None
        npc_persona_id = body.validated_data.get("npc_persona_id")
        if npc_persona_id is not None:
            npc_persona = Persona.objects.filter(pk=npc_persona_id).first()
            if npc_persona is None:
                msg = f"Persona {npc_persona_id} not found."
                raise NotFound(msg)
        character = self._puppet_character(request)
        persona = persona_for_character(character)  # raises on missing sheet
        session = start_interaction(
            role=role, persona=persona, character=character, npc_persona=npc_persona
        )
        _stash(request, session)
        return Response(_serialize_state(session), status=status.HTTP_201_CREATED)

    @extend_schema(
        request=InteractionResolveRequestSerializer,
        responses={
            200: InteractionStateSerializer,
            404: OpenApiResponse(description="No interaction in progress / offer not found."),
            400: OpenApiResponse(description="Offer not eligible / session closed."),
        },
    )
    @action(detail=False, methods=["post"])
    def resolve(self, request: Request) -> Response:
        body = InteractionResolveRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        session = _rehydrate(request)
        offer_id = body.validated_data["offer_id"]
        offer = NPCServiceOffer.objects.filter(pk=offer_id).first()
        if offer is None:
            msg = f"NPCServiceOffer {offer_id} not found."
            raise NotFound(msg)
        try:
            result = resolve_offer(session, offer)
        except ResolveOfferError as exc:
            # Surface the typed exception's ``user_message`` — never
            # ``str(exc)`` (CodeQL: information exposure through an
            # exception; ``feedback_codeql_exceptions``). The internal
            # message identifies the offer + role for logs only.
            raise ValidationError(exc.user_message) from exc
        if session.closed:
            request.session.pop(_SESSION_KEY, None)
        else:
            _stash(request, session)
        return Response(_serialize_state(session, last_result_message=result.message))

    @extend_schema(
        responses={
            200: InteractionStateSerializer,
            404: OpenApiResponse(description="No interaction in progress."),
        },
    )
    @action(detail=False, methods=["post"])
    def end(self, request: Request) -> Response:
        session = _rehydrate(request)
        end_interaction(session)
        request.session.pop(_SESSION_KEY, None)
        return Response(_serialize_state(session))
