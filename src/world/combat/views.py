"""ViewSet for combat encounter management."""

from __future__ import annotations

from http import HTTPMethod
import logging
from typing import TYPE_CHECKING, cast

from django.db.models import Prefetch, Q, QuerySet
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, extend_schema
from evennia.accounts.models import AccountDB
from evennia.objects.models import ObjectDB
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer, Serializer
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from actions.constants import ActionBackend
from actions.errors import ActionDispatchError
from actions.player_interface import dispatch_player_action
from actions.types import ActionRef, ActionResult, DispatchResult
from world.areas.positioning.models import Position
from world.character_sheets.models import CharacterSheet
from world.combat.constants import (
    ClashStatus,
    DuelChallengeStatus,
    EngagementLockStatus,
    OpponentTier,
    ParticipantStatus,
)
from world.combat.filters import (
    CombatEncounterFilter,
    CreatureTemplateFilter,
    DuelChallengeFilter,
    PlacementPersonaFilter,
    PlacementPickFilter,
)
from world.combat.models import (
    Clash,
    CombatEncounter,
    CombatOpponent,
    CombatParticipant,
    CombatRoundAction,
    ComboDefinition,
    ConsiderReading,
    CreaturePhaseTemplate,
    CreatureTemplate,
    DuelChallenge,
    EngagementLock,
    EscalationCurve,
    PendingSelection,
    ThreatPool,
)
from world.combat.permissions import (
    IsEncounterGMOrStaff,
    IsEncounterParticipant,
    IsInEncounterRoom,
)
from world.combat.serializers import (
    ACTIVE_CONDITIONS_CONTEXT_KEY,
    AddOpponentSerializer,
    AddParticipantSerializer,
    ConsiderReadingSerializer,
    CoverSerializer,
    CreatureTemplateSerializer,
    DuelChallengeSerializer,
    EncounterDetailSerializer,
    EncounterListSerializer,
    EncounterSettingsSerializer,
    EscalationCurveSerializer,
    InterposeSerializer,
    JoinEncounterSerializer,
    OpponentDefaultsResponseSerializer,
    OpponentStatBlockSerializer,
    OpponentTargetSerializer,
    ProposeLethalDuelSerializer,
    RemoveOpponentSerializer,
    RemoveParticipantSerializer,
    RoundActionSerializer,
    RoundComboSerializer,
    TauntTargetSerializer,
    ThreatPoolSerializer,
    UpgradeComboSerializer,
    UseItemSerializer,
)
from world.combat.services import (
    add_opponent,
    add_participant,
    end_encounter,
    remove_opponent,
    remove_participant,
    resolve_round,
    scan_round_combos,
    update_encounter_settings,
)
from world.conditions.models import ConditionInstance
from world.covenants.models import CovenantRole
from world.gm.permissions import IsGMOrStaff
from world.items.models import ItemInstance
from world.mechanics.models import Property
from world.scenes.constants import PersonaType, RoundStatus
from world.scenes.models import Persona, Scene
from world.societies.models import Organization
from world.standoffs.serializers import (
    PlacementContextQuerySerializer,
    PlacementContextSerializer,
    PlacementPickSerializer,
    StandoffMoraleRequestSerializer,
)
from world.standoffs.services.state import begin_round_or_break_standoff
from world.stories.pagination import StandardResultsSetPagination

if TYPE_CHECKING:
    from world.stories.models import Story

logger = logging.getLogger(__name__)

# Fixed error messages for API responses (never expose raw exception strings).
_ERR_NOT_PARTICIPANT = "Not a participant in this encounter."
_ERR_NO_ACTION = "No action declared for this round."
_ERR_ALREADY_JOINED = "Already in this encounter."
_ERR_CHARACTER_NOT_YOURS = "You do not currently play that character."
_ERR_ADD_PARTICIPANT = "Failed to add participant."
_ERR_DECLARE_FAILED = "Failed to declare action."
_ERR_INVALID_STATUS = "Encounter is not in a valid status for this action."
_ERR_ALREADY_COMPLETED = "Encounter is already completed."
_ERR_COMBO_UPGRADE = "Cannot upgrade to the requested combo."
_ERR_REMOVE_OPPONENT = "Opponent is not active in this encounter."


class DuelChallengeViewSet(ReadOnlyModelViewSet):
    """Read-only inbox of the requesting player's PENDING duel challenges (#1180).

    Lists every PENDING ``DuelChallenge`` where the caller plays either the
    challenger or the challenged character, so the web UI can render the
    incoming-challenge prompt (and surface a player's outgoing challenges).
    ``?role=incoming|outgoing`` narrows to one side. Scoped to the caller's
    played characters, so it never leaks other players' challenges.
    """

    serializer_class = DuelChallengeSerializer
    queryset = DuelChallenge.objects.none()
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = DuelChallengeFilter
    permission_classes = [IsAuthenticated]

    def get_permissions(self) -> list:
        if self.action == "propose_lethal_duel":
            return [IsAuthenticated(), IsEncounterGMOrStaff()]
        return [IsAuthenticated()]

    def get_queryset(self) -> QuerySet[DuelChallenge]:
        user = self.request.user
        played_ids = user.played_character_sheet_ids
        if not played_ids:
            return DuelChallenge.objects.none()
        return (
            DuelChallenge.objects.filter(status=DuelChallengeStatus.PENDING)
            .filter(Q(challenger_sheet_id__in=played_ids) | Q(challenged_sheet_id__in=played_ids))
            .select_related("challenger_sheet__character", "challenged_sheet__character")
            .order_by("-created_at")
        )

    @extend_schema(request=ProposeLethalDuelSerializer, responses=DuelChallengeSerializer)
    @action(detail=False, methods=[HTTPMethod.POST])
    def propose_lethal_duel(self, request: Request, *args: object, **kwargs: object) -> Response:
        """GM proposes a lethal duel against a named PC (#3068).

        Creates a PENDING, ``is_lethal=True`` ``DuelChallenge`` — no
        ``CombatEncounter`` exists yet. The targeted PC must accept via the
        existing duel-challenge inbox (``accept``/``decline``, same as a
        PvP challenge) before ``create_lethal_duel`` ever runs; a GM cannot
        force this open. Gated to the named scene's GM/owner or staff
        (``IsEncounterGMOrStaff``, widened #3068).
        """
        from world.combat.duels import create_lethal_duel_challenge  # noqa: PLC0415

        serializer = ProposeLethalDuelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        scene = get_object_or_404(Scene, pk=data["scene"])
        challenged_sheet = get_object_or_404(CharacterSheet, pk=data["challenged_sheet_id"])
        pool = get_object_or_404(ThreatPool, pk=data["threat_pool_id"])

        room = scene.room or challenged_sheet.character.db_location
        if room is None:
            return Response(
                {"detail": "No room resolvable for this duel."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            challenge = create_lethal_duel_challenge(
                challenged_sheet,
                room,
                opponent_name=data["opponent_name"],
                tier=data["tier"],
                threat_pool=pool,
            )
        except ValueError:
            return Response(
                {"detail": "Could not propose the lethal duel; check the opponent tier."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        response_serializer = DuelChallengeSerializer(challenge)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class ThreatPoolViewSet(ReadOnlyModelViewSet):
    """Read-only catalog listing for the GM add-opponent picker (#3067).

    ThreatPool is authored content (a named NPC move-set, e.g. "Goblin
    Raiders") — not encounter- or scene-scoped — so this is a flat,
    unfiltered-by-default listing. Any authenticated user may browse it: the
    catalog itself carries nothing sensitive (no encounter state, no player
    data); the sensitive step is spawning an opponent with it, which stays
    gated by ``IsEncounterGMOrStaff`` on ``add_opponent``.
    """

    serializer_class = ThreatPoolSerializer
    queryset = ThreatPool.objects.all().order_by("name")
    pagination_class = StandardResultsSetPagination
    filter_backends = [SearchFilter]
    search_fields = ["name"]
    permission_classes = [IsAuthenticated]


class CreatureTemplateViewSet(ReadOnlyModelViewSet):
    """Read-only bestiary catalog browse for the GM spawn-from-template picker (#3424).

    Mirrors ``checks.CheckTypeViewSet``'s shape (django-filter ``search`` +
    exact-field filter, ``IsGMOrStaff``, standard pagination). Unlike
    ``ThreatPoolViewSet`` (open to any authenticated user — that catalog carries
    no spoiler-sensitive content), the bestiary names authored encounter design
    (boss identity, phase presence) a player shouldn't browse ahead of Consider
    readings / weakness research — see the #3424 spec's leak table.
    """

    queryset = (
        CreatureTemplate.objects.all()
        .select_related("threat_pool")
        .prefetch_related(
            Prefetch(
                "phase_templates",
                queryset=CreaturePhaseTemplate.objects.all(),
                to_attr="cached_phase_templates",
            )
        )
        .order_by("name")
    )
    serializer_class = CreatureTemplateSerializer
    permission_classes = [IsGMOrStaff]
    filter_backends = [DjangoFilterBackend]
    filterset_class = CreatureTemplateFilter
    pagination_class = StandardResultsSetPagination

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "organization",
                int,
                required=False,
                description="Preview the rules inherited through this affiliation instead.",
            )
        ],
        responses=PlacementContextSerializer,
    )
    @action(detail=True, methods=[HTTPMethod.GET], url_path="placement-context")
    def placement_context(self, request: Request, pk: int | None = None) -> Response:
        """The template's standoff profile and inherited faction rules (#4361).

        Read by the beat dialog's and mission studio's placement fields, which show each
        edit beside the template's own value and offer each inherited rule a switch-off.
        """
        from world.standoffs.services.placement import template_context  # noqa: PLC0415

        template = self.get_object()
        # A preview argument of one detail action, not a list filter.
        query = PlacementContextQuerySerializer(data=request.query_params)  # noqa: USE_FILTERSET
        query.is_valid(raise_exception=True)
        organization = query.validated_data.get("organization")
        return Response(PlacementContextSerializer(template_context(template, organization)).data)


class PlacementOrganizationViewSet(ReadOnlyModelViewSet):
    """Organizations a placement can name as its affiliation (#4361), by name.

    The beat dialog's and mission studio's affiliation picker. Same gate as the bestiary
    (``IsGMOrStaff``). A covert organization's existence is itself a secret, so only
    staff see one here.
    """

    serializer_class = PlacementPickSerializer
    permission_classes = [IsGMOrStaff]
    filter_backends = [DjangoFilterBackend]
    filterset_class = PlacementPickFilter
    pagination_class = StandardResultsSetPagination

    def get_queryset(self) -> QuerySet[Organization]:
        queryset = Organization.objects.select_related("org_type").order_by("name")
        if not self.request.user.is_staff:
            queryset = queryset.exclude(is_covert=True)
        return queryset


class PlacementPropertyViewSet(ReadOnlyModelViewSet):
    """Properties a placement can add or edit as a drive (#4361), by name.

    The catalog GMs pick drives from (ADR-0110: GMs adapt authored rows, never invent).
    """

    serializer_class = PlacementPickSerializer
    permission_classes = [IsGMOrStaff]
    filter_backends = [DjangoFilterBackend]
    filterset_class = PlacementPickFilter
    pagination_class = StandardResultsSetPagination
    queryset = Property.objects.order_by("name")


class PlacementPersonaViewSet(ReadOnlyModelViewSet):
    """Named NPCs a GM may stand as an opponent (#4373), by name.

    The beat dialog's and the GM Add Opponent form's named NPC picker. ``?story=`` or
    ``?episode=`` (an owned story, or one of its episodes) or ``?encounter=`` (an encounter
    on one of the story's beats, for its scene GMs) scopes it to the personas that story
    already uses (``story_npc_personas``). Staff see every persona when they name no story.
    A player character who opted in to being read and pressed is offered to any scene GM, with
    or without a story (#4441).
    """

    serializer_class = PlacementPickSerializer
    permission_classes = [IsGMOrStaff]
    filter_backends = [DjangoFilterBackend]
    filterset_class = PlacementPersonaFilter
    pagination_class = StandardResultsSetPagination

    def get_queryset(self) -> QuerySet[Persona]:
        from world.standoffs.services.character_profile import (  # noqa: PLC0415
            opted_in_personas,
        )
        from world.stories.services.cast import story_npc_personas  # noqa: PLC0415

        user = self.request.user
        story, encounter = self._story_and_encounter()
        if story is None:
            if user.is_staff:
                return Persona.objects.order_by("name")
            # An encounter outside any story has no cast, but its scene GMs may still stand a
            # player character who opted in (#4441).
            if (
                encounter is not None
                and encounter.scene is not None
                and encounter.scene.is_gm(user)
            ):
                return Persona.objects.filter(pk__in=opted_in_personas().values("pk")).order_by(
                    "name"
                )
            return Persona.objects.none()
        allowed = (
            user.is_staff
            or story.owners.filter(id=user.id).exists()
            or (
                encounter is not None
                and encounter.scene is not None
                and encounter.scene.is_gm(user)
            )
        )
        if not allowed:
            return Persona.objects.none()
        # A player character who opted in to being read and pressed may be stood by any
        # GM (#4441).
        return Persona.objects.filter(
            Q(pk__in=story_npc_personas(story).values("pk"))
            | Q(pk__in=opted_in_personas().values("pk"))
        ).order_by("name")

    def _story_and_encounter(self) -> tuple[Story | None, CombatEncounter | None]:
        """The story the pick is for, and the encounter it came through (if any)."""
        from world.stories.models import Episode, Story  # noqa: PLC0415

        params = self.request.query_params
        story_id = params.get("story")
        if story_id and story_id.isdigit():
            return Story.objects.filter(pk=int(story_id)).first(), None
        episode_id = params.get("episode")
        if episode_id and episode_id.isdigit():
            episode = (
                Episode.objects.filter(pk=int(episode_id)).select_related("chapter__story").first()
            )
            return (episode.chapter.story if episode is not None else None), None
        encounter_id = params.get("encounter")
        if encounter_id and encounter_id.isdigit():
            encounter = (
                CombatEncounter.objects.filter(pk=int(encounter_id))
                .select_related("story_beat__episode__chapter__story", "scene")
                .first()
            )
            if encounter is not None and encounter.story_beat is not None:
                return encounter.story_beat.episode.chapter.story, encounter
            if encounter is not None:
                return None, encounter
        return None, None


class EscalationCurveViewSet(ReadOnlyModelViewSet):
    """Read-only escalation curve catalog for the GM settings picker (#3552).

    Mirrors ``CreatureTemplateViewSet``'s gate (``IsGMOrStaff``): a curve's
    name and description are authored encounter design a player should not
    browse. ``?search=`` matches the name.
    """

    serializer_class = EscalationCurveSerializer
    queryset = EscalationCurve.objects.all().order_by("name")
    permission_classes = [IsGMOrStaff]
    filter_backends = [SearchFilter]
    search_fields = ["name"]
    pagination_class = StandardResultsSetPagination


class CombatEncounterViewSet(ModelViewSet):
    """ViewSet for combat encounter lifecycle and player actions."""

    filter_backends = [DjangoFilterBackend]
    filterset_class = CombatEncounterFilter
    pagination_class = StandardResultsSetPagination

    def perform_create(self, serializer: BaseSerializer[CombatEncounter]) -> None:
        """Create the encounter, then apply the shared post-creation defaults (#3388).

        The web GM-start-encounter flow (#3067) only supplies ``scene`` — the room
        defaulting and escalation-curve assignment now live in
        ``world.combat.services.finalize_new_encounter``, shared with telnet's
        ``CreateEncounterAction`` so both callers get byte-identical behavior. An
        explicit ``room`` sent by the client always wins (unchanged).
        """
        from world.combat.services import finalize_new_encounter  # noqa: PLC0415

        encounter = serializer.save()
        finalize_new_encounter(encounter)

    def create(self, request: Request, *args: object, **kwargs: object) -> Response:
        """Create, then re-serialize through the prefetch-primed queryset (#3067).

        ``EncounterDetailSerializer``'s nested fields (participants/opponents/
        clashes/etc.) read ``*_cached`` attrs that only exist on instances
        fetched through ``_base_queryset()``'s ``Prefetch(..., to_attr=...)``
        calls. The bare instance ``perform_create`` leaves on ``serializer``
        doesn't carry them, so DRF's default ``CreateModelMixin.create()``
        (serializing that bare instance) raises ``AttributeError`` — this
        endpoint had no caller before the web GM-start-encounter flow, so the
        gap was never exercised.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        encounter = self._base_queryset().get(pk=serializer.instance.pk)
        response = self._serialize_encounter(request, encounter)
        response.status_code = status.HTTP_201_CREATED
        for key, value in self.get_success_headers(serializer.data).items():
            response[key] = value
        return response

    def retrieve(self, request: Request, *args: object, **kwargs: object) -> Response:
        """Serialize the encounter with this request's active conditions in context."""
        encounter = self.get_object()
        context = self.get_serializer_context()
        context[ACTIVE_CONDITIONS_CONTEXT_KEY] = self._active_conditions_by_object_id(encounter)
        return Response(self.get_serializer_class()(encounter, context=context).data)

    def get_permissions(self) -> list:
        if self.action in ("list", "retrieve"):
            return [IsAuthenticated()]
        if self.action == "resolve_selection":
            return [IsAuthenticated()]
        if self.action in (
            "ready",
            "my_action",
            "available_combos",
            "upgrade_combo",
            "revert_combo",
            "flee",
            "cover",
            "interpose",
            "use_item",
            "leave",
            "rally",
            "demoralize",
            "taunt",
            "parley",
            "resolve_selection",
        ):
            return [IsAuthenticated(), IsEncounterParticipant()]
        if self.action == "join":
            return [IsAuthenticated(), IsInEncounterRoom()]
        # GM actions: create, update, destroy, begin_round, resolve_round, etc.
        return [IsAuthenticated(), IsEncounterGMOrStaff()]

    def get_serializer_class(self) -> type[Serializer]:
        if self.action == "list":
            return EncounterListSerializer
        return EncounterDetailSerializer

    def _active_conditions_by_object_id(
        self,
        encounter: CombatEncounter,
    ) -> dict[int, list[ConditionInstance]]:
        """Active ConditionInstances for every fighter in the payload, in one query.

        Keyed by the ObjectDB pk of each participant's character and each
        opponent's objectdb. The filter mirrors ``get_active_conditions``
        (suppression, select_related); visibility filtering and display-priority
        ordering run in the serializer. Loaded per request and passed through
        serializer context (ADR-0260), never left on the idmapper-shared ObjectDB
        (ADR-0263).
        """
        object_ids = {p.character_sheet.character_id for p in encounter.participants_cached}
        object_ids |= {
            o.objectdb_id for o in encounter.opponents_cached if o.objectdb_id is not None
        }
        not_suppressed = Q(is_suppressed=False) | Q(
            suppressed_until__isnull=False,
            suppressed_until__lt=timezone.now(),
        )
        rows = ConditionInstance.objects.filter(
            not_suppressed, target_id__in=object_ids
        ).select_related("condition", "condition__category", "current_stage")
        by_object_id: dict[int, list[ConditionInstance]] = {}
        for row in rows:
            by_object_id.setdefault(row.target_id, []).append(row)
        return by_object_id

    def _base_queryset(self) -> QuerySet[CombatEncounter]:
        from world.areas.positioning.models import (  # noqa: PLC0415
            Position,
            PositionEdge,
            PositionFeature,
        )
        from world.companions.models import CompanionOrder  # noqa: PLC0415

        return CombatEncounter.objects.select_related(
            "scene", "room", "duel_winner__character"
        ).prefetch_related(
            Prefetch(
                "room__positions",
                queryset=Position.objects.order_by("pk")
                .select_related("rampart__element_profile", "terrain__art")
                .prefetch_related(
                    Prefetch(
                        "features",
                        queryset=PositionFeature.objects.select_related("feature_type__art"),
                        to_attr="features_cached",
                    ),
                    Prefetch(
                        "edges_as_a",
                        queryset=PositionEdge.objects.filter(is_passable=True),
                        to_attr="passable_edges_as_a",
                    ),
                    Prefetch(
                        "edges_as_b",
                        queryset=PositionEdge.objects.filter(is_passable=True),
                        to_attr="passable_edges_as_b",
                    ),
                    Prefetch(
                        "edges_as_a",
                        queryset=PositionEdge.objects.select_related(
                            "gating_challenge__template", "source_rampart"
                        ),
                        to_attr="all_edges_as_a",
                    ),
                ),
                to_attr="positions_cached",
            ),
            Prefetch(
                "companion_orders",
                queryset=CompanionOrder.objects.select_related("companion").order_by(
                    "companion_id", "id"
                ),
                to_attr="companion_orders_all_cached",
            ),
            Prefetch(
                "participants",
                queryset=CombatParticipant.objects.select_related(
                    "character_sheet__character",
                    "character_sheet__character__display_data",
                    "character_sheet__active_alternate_self",
                    "character_sheet__active_alternate_self__alternate_self",
                    "character_sheet__character__object_position__position",
                    "character_sheet__vitals",
                    "character_sheet__fatigue",
                    "covenant_role",
                )
                .filter(
                    # Live fights only ever list ACTIVE rows; a COMPLETED encounter
                    # also lists FLED rows, so ParticipantSerializer.aftermath can
                    # reach a FLED participant's own digest (#3551 minor 3) -
                    # deliver_aftermath_digests already sends that participant one.
                    Q(status=ParticipantStatus.ACTIVE)
                    | Q(status=ParticipantStatus.FLED, encounter__status=RoundStatus.COMPLETED)
                )
                .prefetch_related(
                    # Pre-fill CharacterSheet.cached_payload_personas (a
                    # @cached_property doubling as this to_attr target) with the
                    # thumbnail joined, so ParticipantSerializer resolves the PC
                    # portrait with zero per-row queries (#630). Queryset shape
                    # mirrors the property's documented fallback.
                    Prefetch(
                        "character_sheet__personas",
                        queryset=Persona.objects.filter(
                            persona_type__in=[PersonaType.PRIMARY, PersonaType.ESTABLISHED]
                        )
                        .order_by("-persona_type", "created_at", "id")
                        .select_related("thumbnail"),
                        to_attr="cached_payload_personas",
                    ),
                ),
                to_attr="participants_cached",
            ),
            Prefetch(
                "opponents",
                queryset=CombatOpponent.objects.select_related(
                    "persona__thumbnail",
                    "objectdb__object_position__position",
                ),
                to_attr="opponents_cached",
            ),
            Prefetch(
                "clashes",
                queryset=Clash.objects.filter(status=ClashStatus.ACTIVE).select_related(
                    "npc_opponent"
                ),
                to_attr="clashes_cached",
            ),
            Prefetch(
                "engagement_locks",
                queryset=EngagementLock.objects.filter(
                    status=EngagementLockStatus.ACTIVE,
                ).select_related("opponent", "participant"),
                to_attr="engagement_locks_cached",
            ),
        )

    def get_queryset(self) -> QuerySet[CombatEncounter]:
        qs = self._base_queryset().order_by("-created_at")
        if self.action in ("list", "retrieve"):
            return self._filter_readable(qs)
        return qs

    def _filter_readable(self, qs: QuerySet[CombatEncounter]) -> QuerySet[CombatEncounter]:
        """Restrict list/retrieve to encounters whose scene the caller may view.

        Every encounter carries a scene (#1236) and combat participation creates
        a SceneParticipation, so scene-visibility alone covers fighters — no
        participant union is needed. Action routes use the unfiltered base
        queryset and keep their own permission gates.
        """
        user = self.request.user
        if user.is_staff:
            return qs
        return qs.filter(scene__in=Scene.objects.viewable_by(user)).distinct()

    # --- GM Lifecycle Actions ---

    @action(detail=True, methods=[HTTPMethod.POST])
    def begin_round(self, request: Request, pk: int | None = None) -> Response:
        """Begin a new declaration phase."""
        encounter = self.get_object()
        try:
            began = begin_round_or_break_standoff(encounter, initiated_by_pc_side=None)
        except ValueError:
            return Response(
                {"detail": _ERR_INVALID_STATUS},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not began:
            return Response(
                {"detail": "The standoff has already ended."},
                status=status.HTTP_409_CONFLICT,
            )
        # Service updates encounter in place via refresh_from_db
        return self._serialize_encounter(request, encounter)

    @action(detail=True, methods=[HTTPMethod.POST])
    def resolve_round(self, request: Request, pk: int | None = None) -> Response:
        """Resolve the current round.

        SharedMemoryModel identity map means all .save() calls during
        resolution update the same Python objects in participants_cached
        and opponents_cached — no re-fetch needed.
        """
        encounter = self.get_object()
        try:
            resolve_round(encounter)
        except ActionDispatchError as exc:
            return Response(
                {"detail": exc.user_message},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except ValueError:
            return Response(
                {"detail": _ERR_INVALID_STATUS},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return self._serialize_encounter(request, encounter)

    @action(detail=True, methods=[HTTPMethod.POST])
    def add_participant(self, request: Request, pk: int | None = None) -> Response:
        """Add a PC to the encounter (GM action)."""
        encounter = self.get_object()
        serializer = AddParticipantSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        sheet = get_object_or_404(
            CharacterSheet,
            pk=serializer.validated_data["character_sheet_id"],
        )
        covenant_role = None
        role_id = serializer.validated_data.get("covenant_role_id")
        if role_id:
            covenant_role = get_object_or_404(CovenantRole, pk=role_id)
        try:
            new_participant = add_participant(
                encounter,
                sheet,
                covenant_role=covenant_role,
            )
        except Exception:
            logger.exception(
                "add_participant failed for encounter %s sheet %s", encounter.pk, sheet.pk
            )
            return Response(
                {"detail": _ERR_ADD_PARTICIPANT},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Update cached participant list in-place
        encounter.participants_cached.append(new_participant)
        return self._serialize_encounter(request, encounter)

    @action(detail=True, methods=[HTTPMethod.POST])
    def remove_participant(
        self,
        request: Request,
        pk: int | None = None,
    ) -> Response:
        """Remove a PC from the encounter (GM action)."""
        encounter = self.get_object()
        serializer = RemoveParticipantSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        participant_id = serializer.validated_data["participant_id"]
        participant = get_object_or_404(
            CombatParticipant,
            pk=participant_id,
            encounter=encounter,
        )
        remove_participant(participant)
        # Remove from cached list (prefetch only loads ACTIVE)
        encounter.participants_cached = [
            p for p in encounter.participants_cached if p.pk != participant.pk
        ]
        return self._serialize_encounter(request, encounter)

    @extend_schema(request=AddOpponentSerializer)
    @action(detail=True, methods=[HTTPMethod.POST])
    def add_opponent(self, request: Request, pk: int | None = None) -> Response:
        """Add an NPC opponent to the encounter (GM action)."""
        from world.combat.scaling import NPCUnderCustodyError  # noqa: PLC0415

        encounter = self.get_object()
        serializer = AddOpponentSerializer(
            data=request.data,
            context={"encounter": encounter, "request": request},
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        pool = get_object_or_404(ThreatPool, pk=data["threat_pool_id"])
        position = None
        position_id = data.get("position_id")
        if position_id is not None:
            position = get_object_or_404(Position, pk=position_id)
        # #2001 Task 5: this is a GM-facing web path (not action-dispatch), so
        # the requesting account is threaded directly rather than resolved
        # from a puppeted actor; a named NPC (#4373) goes through
        # add_opponent's custody APPEAR gate with it.
        try:
            new_opponent = add_opponent(
                encounter,
                name=data["name"],
                tier=data["tier"],
                max_health=data.get("max_health"),
                threat_pool=pool,
                description=data.get("description", ""),
                soak_value=data.get("soak_value"),
                probing_threshold=data.get("probing_threshold"),
                level=data.get("level"),
                acting_account=cast(AccountDB, request.user),
                position=position,
                persona=data.get("persona"),
            )
        except NPCUnderCustodyError as exc:
            return Response(
                {"detail": exc.user_message},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Update cached opponent list in-place
        encounter.opponents_cached.append(new_opponent)
        return self._serialize_encounter(request, encounter)

    @action(detail=True, methods=[HTTPMethod.POST])
    def remove_opponent(self, request: Request, pk: int | None = None) -> Response:
        """Remove an NPC opponent from the encounter (GM action, #3382)."""
        encounter = self.get_object()
        serializer = RemoveOpponentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        opponent_id = serializer.validated_data["opponent_id"]
        opponent = get_object_or_404(
            CombatOpponent,
            pk=opponent_id,
            encounter=encounter,
        )
        try:
            remove_opponent(opponent)
        except ValueError:
            return Response(
                {"detail": _ERR_REMOVE_OPPONENT},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Remove from cached list (prefetch only loads ACTIVE)
        encounter.opponents_cached = [o for o in encounter.opponents_cached if o.pk != opponent.pk]
        return self._serialize_encounter(request, encounter)

    @extend_schema(
        parameters=[
            OpenApiParameter("tier", str, OpenApiParameter.QUERY, required=True),
        ],
        responses=OpponentDefaultsResponseSerializer,
    )
    @action(
        detail=True,
        methods=[HTTPMethod.GET],
        url_path="opponent-defaults",
        permission_classes=[IsAuthenticated, IsEncounterGMOrStaff],
    )
    def opponent_defaults(self, request: Request, pk: int | None = None) -> Response:
        """Preview the scaling formula output for a given tier (GM action).

        Returns the computed OpponentStatBlock fields alongside ``stakes_ok``
        and ``stakes_message`` so the GM can see both the stat budget and
        whether the stakes gate would block a real add_opponent call.

        Query params:
            tier: An ``OpponentTier`` value (required).

        Returns:
            200 with block fields + ``stakes_ok`` + ``stakes_message`` (never 400
            for the stakes gate — preview must explain the gate, not block).
            400 when ``tier`` is missing or not a valid ``OpponentTier``.
        """
        from world.combat.scaling import (  # noqa: PLC0415
            StakesRequirementError,
            compute_opponent_stat_block,
            validate_stakes_requirement,
        )

        # Resolve the object first so non-GMs get 403 before tier validation.
        encounter = self.get_object()

        tier = request.query_params.get("tier")  # noqa: USE_FILTERSET
        valid_tiers = {choice[0] for choice in OpponentTier.choices}
        if not tier or tier not in valid_tiers:
            return Response(
                {"tier": f"Must be one of: {', '.join(sorted(valid_tiers))}."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        block = compute_opponent_stat_block(tier, encounter)

        stakes_ok: bool
        stakes_message: str
        try:
            validate_stakes_requirement(encounter, cast(AccountDB, request.user))
            stakes_ok = True
            stakes_message = ""
        except StakesRequirementError as exc:
            stakes_ok = False
            stakes_message = exc.user_message

        data = {
            **OpponentStatBlockSerializer(block).data,
            "stakes_ok": stakes_ok,
            "stakes_message": stakes_message,
        }
        return Response(data, status=status.HTTP_200_OK)

    @action(detail=True, methods=[HTTPMethod.POST])
    def pause(self, request: Request, pk: int | None = None) -> Response:
        """Pause or unpause the encounter timer."""
        encounter = self.get_object()
        encounter.is_paused = not encounter.is_paused
        encounter.save(update_fields=["is_paused"])
        # save() updates the identity map — no re-fetch needed
        return self._serialize_encounter(request, encounter)

    @action(detail=True, methods=[HTTPMethod.PATCH], url_path="settings")
    def update_settings(self, request: Request, pk: int | None = None) -> Response:
        """GM: change stakes/risk/pace/timer on a live encounter (#3383).

        Named ``update_settings`` rather than ``settings`` — ``APIView`` sets a
        class attribute ``settings = api_settings`` (DRF's own settings
        accessor, read by ``get_format_suffix``/``get_exception_handler``/etc.
        via ``self.settings``); a same-named action method would shadow it on
        the instance and break every other action on this ViewSet with
        ``AttributeError: 'function' object has no attribute '...'``. The URL
        stays ``/api/combat/{id}/settings/`` via ``url_path``.
        """
        encounter = self.get_object()
        serializer = EncounterSettingsSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        update_encounter_settings(encounter, **serializer.validated_data)
        return self._serialize_encounter(request, encounter)

    @extend_schema(request=StandoffMoraleRequestSerializer, responses=EncounterDetailSerializer)
    @action(detail=True, methods=[HTTPMethod.POST], url_path="standoff-morale")
    def standoff_morale(self, request: Request, pk: int | None = None) -> Response:
        """GM: shake or steady one standoff group by one morale state, with a reason (#4354)."""
        from actions.definitions.gm_standoff import GMStandoffMoraleAction  # noqa: PLC0415

        encounter = self.get_object()
        body = StandoffMoraleRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        group = get_object_or_404(
            encounter.standoff_groups.all(), pk=body.validated_data["group_id"]
        )
        result = GMStandoffMoraleAction().run(
            actor=None,
            account=request.user,
            group_id=group.pk,
            direction=body.validated_data["direction"],
            reason=body.validated_data["reason"],
        )
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        return self._serialize_encounter(request, encounter)

    @extend_schema(request=None, responses=EncounterDetailSerializer)
    @action(detail=True, methods=[HTTPMethod.POST], url_path="open-standoff")
    def open_standoff(self, request: Request, pk: int | None = None) -> Response:
        """GM: open a standoff on an encounter that has not begun round one (#4354)."""
        from actions.definitions.gm_standoff import GMOpenStandoffAction  # noqa: PLC0415

        encounter = self.get_object()
        result = GMOpenStandoffAction().run(
            actor=None, account=request.user, encounter_id=encounter.pk
        )
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        return self._serialize_encounter(request, encounter)

    @action(detail=True, methods=[HTTPMethod.POST])
    def end(self, request: Request, pk: int | None = None) -> Response:
        """GM: force-end the encounter as ABANDONED (#876)."""
        encounter = self.get_object()
        if encounter.status == RoundStatus.COMPLETED:
            return Response(
                {"detail": _ERR_ALREADY_COMPLETED},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            end_encounter(encounter)
        except ValueError:
            # Concurrent double-end: the seam's atomic guard fired after our
            # status read. Re-check so an unrelated ValueError from the seam's
            # tail isn't misreported as already-completed.
            encounter.refresh_from_db()
            if encounter.status != RoundStatus.COMPLETED:
                raise
            return Response(
                {"detail": _ERR_ALREADY_COMPLETED},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return self._serialize_encounter(request, encounter)

    # --- Player Actions ---

    @action(detail=True, methods=[HTTPMethod.POST])
    def ready(self, request: Request, pk: int | None = None) -> Response:
        """Toggle ready status for the current round."""
        encounter = self.get_object()
        participant = self._get_participant(request, encounter)
        if not participant:
            return Response(
                {"detail": _ERR_NOT_PARTICIPANT},
                status=status.HTTP_403_FORBIDDEN,
            )
        current_action = self._current_round_action(participant, encounter)
        if not current_action:
            return Response(
                {"detail": _ERR_NO_ACTION},
                status=status.HTTP_400_BAD_REQUEST,
            )
        self._dispatch_combat_action(participant.character_sheet.character, "combat_ready")
        return self._serialize_encounter(request, encounter)

    @action(detail=True, methods=[HTTPMethod.GET])
    def my_action(self, request: Request, pk: int | None = None) -> Response:
        """Get the current user's action for this round."""
        encounter = self.get_object()
        participant = self._get_participant(request, encounter)
        if not participant:
            return Response(
                {"detail": _ERR_NOT_PARTICIPANT},
                status=status.HTTP_403_FORBIDDEN,
            )
        action_obj = self._current_round_action(participant, encounter)
        if not action_obj:
            return Response(None)
        return Response(RoundActionSerializer(action_obj).data)

    @extend_schema(responses={200: RoundComboSerializer(many=True)})
    @action(detail=True, methods=[HTTPMethod.GET], pagination_class=None, filter_backends=[])
    def available_combos(
        self,
        request: Request,
        pk: int | None = None,
    ) -> Response:
        """List the combos taking shape this round, slot by slot (#3553).

        Complete fills are the upgrade candidates; partial fills of a known
        combo show which slots are still open.
        """
        encounter = self.get_object()
        combos = scan_round_combos(encounter, encounter.round_number)
        return Response(RoundComboSerializer(combos, many=True).data)

    @action(detail=True, methods=[HTTPMethod.POST])
    def upgrade_combo(self, request: Request, pk: int | None = None) -> Response:
        """Upgrade own action to a combo."""
        encounter = self.get_object()
        participant = self._get_participant(request, encounter)
        if not participant:
            return Response(
                {"detail": _ERR_NOT_PARTICIPANT},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = UpgradeComboSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        combo_id = serializer.validated_data["combo_id"]
        get_object_or_404(ComboDefinition, pk=combo_id)
        current_action = self._current_round_action(participant, encounter)
        if not current_action:
            return Response(
                {"detail": _ERR_NO_ACTION},
                status=status.HTTP_400_BAD_REQUEST,
            )
        result = self._dispatch_combat_action(
            participant.character_sheet.character,
            "combat_combo",
            {"combo_id": combo_id},
        )
        if not self._action_succeeded(result):
            return Response(
                {"detail": _ERR_COMBO_UPGRADE},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return self._serialize_encounter(request, encounter)

    @action(detail=True, methods=[HTTPMethod.POST])
    def revert_combo(self, request: Request, pk: int | None = None) -> Response:
        """Revert combo upgrade on own action."""
        encounter = self.get_object()
        participant = self._get_participant(request, encounter)
        if not participant:
            return Response(
                {"detail": _ERR_NOT_PARTICIPANT},
                status=status.HTTP_403_FORBIDDEN,
            )
        current_action = self._current_round_action(participant, encounter)
        if not current_action:
            return Response(
                {"detail": _ERR_NO_ACTION},
                status=status.HTTP_400_BAD_REQUEST,
            )
        self._dispatch_combat_action(participant.character_sheet.character, "combat_revert")
        return self._serialize_encounter(request, encounter)

    # --- Participation ---

    @action(detail=True, methods=[HTTPMethod.POST])
    def join(self, request: Request, pk: int | None = None) -> Response:
        """Player self-joins the encounter as the specified character.

        Requires an explicit ``character_sheet_id`` in the request body;
        never auto-selects a character. The chosen sheet must belong to
        an active roster tenure for the requesting user.

        **No staff bypass on the ownership check.** Staff users who want
        to put a character into an encounter use the GM-side
        ``add_participant`` action — which lets them name any
        character_sheet without an ownership requirement. ``join`` is the
        self-service "act as my own character" entry point, and the
        ownership check applies to staff identically to players.
        """
        encounter = self.get_object()
        serializer = JoinEncounterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        sheet_pk = serializer.validated_data["character_sheet_id"]
        if sheet_pk not in self._viewer_character_ids(request):
            return Response(
                {"detail": _ERR_CHARACTER_NOT_YOURS},
                status=status.HTTP_403_FORBIDDEN,
            )
        sheet = get_object_or_404(CharacterSheet, pk=sheet_pk)
        result = self._dispatch_combat_action(
            sheet.character,
            "combat_join",
            {"encounter_id": encounter.pk, "character_sheet_id": sheet.pk},
        )
        if not self._action_succeeded(result):
            return Response(
                {"detail": _ERR_ALREADY_JOINED},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Refresh the cached participant list with the newly-created row.
        new_participant = CombatParticipant.objects.filter(
            encounter=encounter,
            character_sheet=sheet,
            status=ParticipantStatus.ACTIVE,
        ).first()
        if new_participant is not None:
            encounter.participants_cached.append(new_participant)
        return self._serialize_encounter(request, encounter)

    @action(detail=True, methods=[HTTPMethod.POST])
    def flee(self, request: Request, pk: int | None = None) -> Response:
        """Declare intent to flee.

        Creates a passives-only action with maneuver=FLEE. Flee resolves as
        a check at round resolution; the participant remains ACTIVE until then.
        """
        encounter = self.get_object()
        participant = self._get_participant(request, encounter)
        if not participant:
            return Response(
                {"detail": _ERR_NOT_PARTICIPANT},
                status=status.HTTP_403_FORBIDDEN,
            )
        result = self._dispatch_combat_action(participant.character_sheet.character, "combat_flee")
        if not self._action_succeeded(result):
            return Response(
                {"detail": _ERR_DECLARE_FAILED},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return self._serialize_encounter(request, encounter)

    @action(detail=True, methods=[HTTPMethod.POST])
    def leave(self, request: Request, pk: int | None = None) -> Response:
        """Player voluntarily leaves an Open Encounter between rounds.

        Only valid in BETWEEN_ROUNDS status. If the departing player is the last
        active participant, the encounter completes as ABANDONED.
        """
        encounter = self.get_object()
        participant = self._get_participant(request, encounter)
        if not participant:
            return Response(
                {"detail": _ERR_NOT_PARTICIPANT},
                status=status.HTTP_403_FORBIDDEN,
            )
        result = self._dispatch_combat_action(participant.character_sheet.character, "combat_leave")
        if not self._action_succeeded(result):
            return Response(
                {"detail": _ERR_INVALID_STATUS},
                status=status.HTTP_400_BAD_REQUEST,
            )
        encounter.participants_cached = [
            p for p in encounter.participants_cached if p.pk != participant.pk
        ]
        return self._serialize_encounter(request, encounter)

    @action(detail=True, methods=[HTTPMethod.POST])
    def cover(self, request: Request, pk: int | None = None) -> Response:
        """Declare a covering maneuver for an ally.

        Creates a passives-only action with maneuver=COVER and
        focused_ally_target set to the named ally. The participant remains
        ACTIVE; cover resolves at round resolution as a bonus to the ally's
        flee check.
        """
        encounter = self.get_object()
        participant = self._get_participant(request, encounter)
        if not participant:
            return Response(
                {"detail": _ERR_NOT_PARTICIPANT},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = CoverSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ally_id = serializer.validated_data["ally_participant_id"]
        ally = get_object_or_404(CombatParticipant, pk=ally_id, encounter=encounter)
        result = self._dispatch_combat_action(
            participant.character_sheet.character,
            "combat_cover",
            {"ally_participant_id": ally.pk},
        )
        if not self._action_succeeded(result):
            return Response(
                {"detail": _ERR_DECLARE_FAILED},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return self._serialize_encounter(request, encounter)

    @action(detail=True, methods=[HTTPMethod.POST])
    def use_item(self, request: Request, pk: int | None = None) -> Response:
        """Declare using a held on-use item as this round's action (#2023, #2120).

        A primary maneuver with maneuver=USE_ITEM and item_instance set to the
        named ``ItemInstance`` -- mutually exclusive with a declared focused
        technique, unlike the passives-only cover/interpose declarations. At
        most one of ``target_participant_id`` (an ally) / ``target_opponent_id``
        (an NPC opponent) may be supplied.
        """
        encounter = self.get_object()
        participant = self._get_participant(request, encounter)
        if not participant:
            return Response(
                {"detail": _ERR_NOT_PARTICIPANT},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = UseItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item_instance = get_object_or_404(
            ItemInstance, pk=serializer.validated_data["item_instance_id"]
        )
        ally_id = serializer.validated_data.get("target_participant_id")
        opponent_id = serializer.validated_data.get("target_opponent_id")
        action_kwargs: dict = {"item_instance_id": item_instance.pk}
        if ally_id is not None:
            ally = get_object_or_404(CombatParticipant, pk=ally_id, encounter=encounter)
            action_kwargs["ally_participant_id"] = ally.pk
        elif opponent_id is not None:
            opponent = get_object_or_404(CombatOpponent, pk=opponent_id, encounter=encounter)
            action_kwargs["opponent_id"] = opponent.pk
        result = self._dispatch_combat_action(
            participant.character_sheet.character,
            "combat_use",
            action_kwargs,
        )
        if not self._action_succeeded(result):
            return Response(
                {"detail": _ERR_DECLARE_FAILED},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return self._serialize_encounter(request, encounter)

    @action(detail=True, methods=[HTTPMethod.POST])
    def interpose(self, request: Request, pk: int | None = None) -> Response:
        """Declare an interposing maneuver, optionally guarding a named ally.

        Creates a passives-only action with maneuver=INTERPOSE. When
        ``ally_participant_id`` is omitted or null, the participant guards any
        ally hit this round (``focused_ally_target=None``). When provided, the
        ally must be an active participant in this encounter.
        """
        encounter = self.get_object()
        participant = self._get_participant(request, encounter)
        if not participant:
            return Response(
                {"detail": _ERR_NOT_PARTICIPANT},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = InterposeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ally_id = serializer.validated_data.get("ally_participant_id")
        ally = (
            get_object_or_404(CombatParticipant, pk=ally_id, encounter=encounter)
            if ally_id is not None
            else None
        )
        result = self._dispatch_combat_action(
            participant.character_sheet.character,
            "combat_interpose",
            {"ally_participant_id": ally.pk if ally is not None else None},
        )
        if not self._action_succeeded(result):
            return Response(
                {"detail": _ERR_DECLARE_FAILED},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return self._serialize_encounter(request, encounter)

    @action(detail=True, methods=[HTTPMethod.POST])
    def rally(self, request: Request, pk: int | None = None) -> Response:
        """Declare a rallying maneuver to inspire an ally (#2015).

        Requires ``ally_participant_id`` — the PK of the active ally to inspire.
        """
        encounter = self.get_object()
        participant = self._get_participant(request, encounter)
        if not participant:
            return Response(
                {"detail": _ERR_NOT_PARTICIPANT},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = CoverSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ally_id = serializer.validated_data.get("ally_participant_id")
        ally = get_object_or_404(CombatParticipant, pk=ally_id, encounter=encounter)
        result = self._dispatch_combat_action(
            participant.character_sheet.character,
            "combat_rally",
            {"ally_participant_id": ally.pk},
        )
        if not self._action_succeeded(result):
            return Response(
                {"detail": _ERR_DECLARE_FAILED},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return self._serialize_encounter(request, encounter)

    @action(detail=True, methods=[HTTPMethod.POST])
    def demoralize(self, request: Request, pk: int | None = None) -> Response:
        """Declare a demoralizing maneuver against an opponent (#2015).

        Requires ``opponent_id`` — the PK of the active opponent to demoralize.
        """
        encounter = self.get_object()
        participant = self._get_participant(request, encounter)
        if not participant:
            return Response(
                {"detail": _ERR_NOT_PARTICIPANT},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = OpponentTargetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        opponent_id = serializer.validated_data.get("opponent_id")
        get_object_or_404(CombatOpponent, pk=opponent_id, encounter=encounter)
        result = self._dispatch_combat_action(
            participant.character_sheet.character,
            "combat_demoralize",
            {"opponent_id": opponent_id},
        )
        if not self._action_succeeded(result):
            return Response(
                {"detail": _ERR_DECLARE_FAILED},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return self._serialize_encounter(request, encounter)

    @extend_schema(request=TauntTargetSerializer, responses=EncounterDetailSerializer)
    @action(detail=True, methods=[HTTPMethod.POST])
    def taunt(self, request: Request, pk: int | None = None) -> Response:
        """Declare a taunting maneuver against an opponent or an ally (#2015, #4737).

        Requires exactly one of ``opponent_id`` (an active opponent, drawing its aggro)
        or ``participant_id`` (an active ally, goaded into a rolled surge).
        """
        encounter = self.get_object()
        participant = self._get_participant(request, encounter)
        if not participant:
            return Response(
                {"detail": _ERR_NOT_PARTICIPANT},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = TauntTargetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        opponent_id = serializer.validated_data.get("opponent_id")
        ally_id = serializer.validated_data.get("participant_id")
        if ally_id is not None:
            ally = get_object_or_404(CombatParticipant, pk=ally_id, encounter=encounter)
            action_kwargs: dict = {"ally_participant_id": ally.pk}
        else:
            get_object_or_404(CombatOpponent, pk=opponent_id, encounter=encounter)
            action_kwargs = {"opponent_id": opponent_id}
        result = self._dispatch_combat_action(
            participant.character_sheet.character,
            "combat_taunt",
            action_kwargs,
        )
        if not self._action_succeeded(result):
            return Response(
                {"detail": _ERR_DECLARE_FAILED},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return self._serialize_encounter(request, encounter)

    @action(detail=True, methods=[HTTPMethod.POST])
    def parley(self, request: Request, pk: int | None = None) -> Response:
        """Declare a parley attempt against an opponent (#2015).

        Requires ``opponent_id`` — the PK of the active opponent to parley with.
        """
        encounter = self.get_object()
        participant = self._get_participant(request, encounter)
        if not participant:
            return Response(
                {"detail": _ERR_NOT_PARTICIPANT},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = OpponentTargetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        opponent_id = serializer.validated_data.get("opponent_id")
        get_object_or_404(CombatOpponent, pk=opponent_id, encounter=encounter)
        result = self._dispatch_combat_action(
            participant.character_sheet.character,
            "combat_parley",
            {"opponent_id": opponent_id},
        )
        if not self._action_succeeded(result):
            return Response(
                {"detail": _ERR_DECLARE_FAILED},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return self._serialize_encounter(request, encounter)

    @action(detail=True, methods=[HTTPMethod.POST], url_path="resolve-selection")
    def resolve_selection(self, request: Request, pk: int | None = None) -> Response:
        """Resolve a player-owned specialist choice from the browser (#3915)."""
        encounter = self.get_object()
        selection_id = request.data.get("selection_id")
        option_id = request.data.get("option_id")
        if not isinstance(selection_id, int) or not isinstance(option_id, str):
            return Response({"detail": "A selection and option are required."}, status=400)
        selection = get_object_or_404(
            PendingSelection.objects.select_related("participant__character_sheet"),
            pk=selection_id,
            encounter=encounter,
        )
        participant = self._get_participant(request, encounter)
        if participant is None or (
            not request.user.is_staff
            and not encounter.scene.is_gm(request.user)
            and selection.participant_id != participant.pk
        ):
            return Response({"detail": _ERR_NOT_PARTICIPANT}, status=status.HTTP_403_FORBIDDEN)
        from world.combat.constants import SelectionType  # noqa: PLC0415

        if selection.selection_type != SelectionType.WEAKNESS:
            return Response({"detail": "This selection cannot be resolved here."}, status=400)
        from world.covenants.weakness import resolve_weakness_selection  # noqa: PLC0415

        if not resolve_weakness_selection(selection, option_id):
            return Response(
                {"detail": "That specialist choice is no longer available."}, status=400
            )
        return self._serialize_encounter(request, encounter)

    @action(
        detail=True,
        methods=[HTTPMethod.GET],
        url_path=r"consider/(?P<opponent_pk>\d+)",
    )
    def consider(
        self,
        request: Request,
        pk: int | None = None,
        opponent_pk: str | None = None,
    ) -> Response:
        """Assess an opponent's threat level (#2716).

        GET /api/combat/encounters/<pk>/consider/<opponent_pk>/
        Returns narrative prose — never the check mechanics.
        """
        from world.combat.consider import consider_opponent  # noqa: PLC0415

        encounter = self.get_object()
        opponent = get_object_or_404(CombatOpponent, pk=opponent_pk, encounter=encounter)
        participant = self._get_participant(request, encounter)
        if not participant:
            return Response(
                {"detail": _ERR_NOT_PARTICIPANT},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Check for cached reading before running the check.
        is_cached = ConsiderReading.objects.filter(
            participant=participant, opponent=opponent
        ).exists()

        reading = consider_opponent(participant, opponent)
        serializer = ConsiderReadingSerializer(reading, context={"is_cached": is_cached})
        return Response(serializer.data)

    # --- Helpers ---

    def _viewer_character_ids(self, request: Request) -> frozenset[int]:
        """Return character_sheet ids the request user currently plays.

        Reads the cached property on ``request.user`` (the ``Account``
        typeclass exposes ``played_character_sheet_ids``); falls back to
        an empty set for anonymous / non-Account users.
        """
        try:
            return request.user.played_character_sheet_ids
        except AttributeError:
            return frozenset()

    def _serialize_encounter(
        self,
        request: Request,
        encounter: CombatEncounter,
    ) -> Response:
        """Serialize the encounter as-is — no re-fetch.

        Use when the encounter's cached state (participants_cached,
        opponents_cached) is still valid. Most endpoints that only
        touch actions or encounter fields use this.
        """
        context = self._build_serializer_context(request, encounter)
        return Response(
            EncounterDetailSerializer(encounter, context=context).data,
        )

    def _build_serializer_context(
        self,
        request: Request,
        encounter: CombatEncounter,
    ) -> dict:
        """Build serializer context with pre-computed, cached values.

        Computes viewer_character_ids and is_gm once. All serializers
        and nested serializers read from this context — zero redundant
        queries.
        """
        context: dict = {"request": request}
        context["viewer_character_ids"] = self._viewer_character_ids(request)

        is_gm = False
        if request.user.is_authenticated and not request.user.is_staff and encounter.scene:
            is_gm = encounter.scene.is_gm(request.user)
        context["is_gm"] = bool(request.user.is_authenticated and request.user.is_staff) or is_gm
        context[ACTIVE_CONDITIONS_CONTEXT_KEY] = self._active_conditions_by_object_id(encounter)

        return context

    def _current_round_action(
        self,
        participant: CombatParticipant,
        encounter: CombatEncounter,
    ) -> CombatRoundAction | None:
        """Return the participant's CombatRoundAction for the current round.

        Uses ``.first()`` because the unique constraint
        ``unique_action_per_participant_per_round`` (see
        ``CombatRoundAction.Meta``) guarantees at most one row per
        ``(participant, round_number)`` — no ordering needed.
        """
        return CombatRoundAction.objects.filter(
            participant=participant,
            round_number=encounter.round_number,
        ).first()

    def _get_participant(
        self,
        request: Request,
        encounter: CombatEncounter,
    ) -> CombatParticipant | None:
        """Get the requesting user's active participant from cached data.

        Walks ``participants_cached`` (prefetched on the encounter) and
        reads ``viewer_character_ids`` from the per-request cache — no
        new DB queries when the encounter is warm.
        """
        character_ids = self._viewer_character_ids(request)
        return next(
            (
                p
                for p in encounter.participants_cached
                if p.character_sheet.character_id in character_ids
            ),
            None,
        )

    def _dispatch_combat_action(
        self,
        actor: ObjectDB,
        registry_key: str,
        action_kwargs: dict | None = None,
    ) -> DispatchResult:
        """Run a registry combat action through the shared ``dispatch_player_action`` seam.

        The web and telnet now converge on the same Action; the viewset keeps its
        request-scoped ownership/participant checks and serialized-encounter contract.
        """
        ref = ActionRef(backend=ActionBackend.REGISTRY, registry_key=registry_key)
        return dispatch_player_action(actor, ref, action_kwargs or {})

    @staticmethod
    def _action_succeeded(result: DispatchResult) -> bool:
        """True when a REGISTRY dispatch ran its action and it reported success."""
        return isinstance(result.detail, ActionResult) and result.detail.success
