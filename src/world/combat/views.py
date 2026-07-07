"""ViewSet for combat encounter management."""

from __future__ import annotations

from http import HTTPMethod
from typing import cast

from django.db.models import Prefetch, Q, QuerySet
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, extend_schema
from evennia.accounts.models import AccountDB
from evennia.objects.models import ObjectDB
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import Serializer
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
    OpponentTier,
    ParticipantStatus,
)
from world.combat.filters import CombatEncounterFilter, DuelChallengeFilter
from world.combat.models import (
    Clash,
    CombatEncounter,
    CombatOpponent,
    CombatParticipant,
    CombatRoundAction,
    ComboDefinition,
    DuelChallenge,
    ThreatPool,
)
from world.combat.permissions import (
    IsEncounterGMOrStaff,
    IsEncounterParticipant,
    IsInEncounterRoom,
)
from world.combat.serializers import (
    ACTIVE_CONDITIONS_CACHE_ATTR,
    AddOpponentSerializer,
    AddParticipantSerializer,
    CoverSerializer,
    DuelChallengeSerializer,
    EncounterDetailSerializer,
    EncounterListSerializer,
    InterposeSerializer,
    JoinEncounterSerializer,
    OpponentDefaultsResponseSerializer,
    OpponentStatBlockSerializer,
    RemoveParticipantSerializer,
    RoundActionSerializer,
    UpgradeComboSerializer,
)
from world.combat.services import (
    add_opponent,
    add_participant,
    begin_declaration_phase,
    end_encounter,
    remove_participant,
    resolve_round,
    run_combo_detection,
)
from world.conditions.models import ConditionInstance
from world.covenants.models import CovenantRole
from world.scenes.constants import PersonaType, RoundStatus
from world.scenes.models import Persona, Scene
from world.stories.pagination import StandardResultsSetPagination

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

    def get_queryset(self) -> QuerySet[DuelChallenge]:
        user = self.request.user
        played_ids = getattr(user, "played_character_sheet_ids", frozenset())  # noqa: GETATTR_LITERAL
        if not played_ids:
            return DuelChallenge.objects.none()
        return (
            DuelChallenge.objects.filter(status=DuelChallengeStatus.PENDING)
            .filter(Q(challenger_sheet_id__in=played_ids) | Q(challenged_sheet_id__in=played_ids))
            .select_related("challenger_sheet__character", "challenged_sheet__character")
            .order_by("-created_at")
        )


class CombatEncounterViewSet(ModelViewSet):
    """ViewSet for combat encounter lifecycle and player actions."""

    filter_backends = [DjangoFilterBackend]
    filterset_class = CombatEncounterFilter
    pagination_class = StandardResultsSetPagination

    def get_permissions(self) -> list:
        if self.action in ("list", "retrieve"):
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
            "leave",
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

    def _active_conditions_prefetch(self, lookup: str) -> Prefetch:
        """Prefetch active ConditionInstances onto a target ObjectDB.

        ``lookup`` is the relation path to the ObjectDB whose conditions we
        want (``character_sheet__character`` for participants,
        ``objectdb`` for opponents). The queryset mirrors
        ``get_active_conditions`` — same suppression filter and
        select_related — and lands on
        ``ACTIVE_CONDITIONS_CACHE_ATTR`` so the serializer reads it
        without an N+1. Visibility filtering + display-priority ordering
        run in Python in the serializer.
        """
        not_suppressed = Q(is_suppressed=False) | Q(
            suppressed_until__isnull=False,
            suppressed_until__lt=timezone.now(),
        )
        condition_qs = ConditionInstance.objects.filter(not_suppressed).select_related(
            "condition",
            "condition__category",
            "current_stage",
        )
        return Prefetch(
            f"{lookup}__condition_instances",
            queryset=condition_qs,
            to_attr=ACTIVE_CONDITIONS_CACHE_ATTR,
        )

    def _base_queryset(self) -> QuerySet[CombatEncounter]:
        from world.areas.positioning.models import Position, PositionEdge  # noqa: PLC0415

        return CombatEncounter.objects.select_related(
            "scene", "room", "duel_winner__character"
        ).prefetch_related(
            Prefetch(
                "room__positions",
                queryset=Position.objects.order_by("pk").prefetch_related(
                    Prefetch(
                        "edges_as_a",
                        queryset=PositionEdge.objects.filter(is_passable=True).only(
                            "position_a_id", "position_b_id"
                        ),
                        to_attr="passable_edges_as_a",
                    ),
                    Prefetch(
                        "edges_as_b",
                        queryset=PositionEdge.objects.filter(is_passable=True).only(
                            "position_a_id", "position_b_id"
                        ),
                        to_attr="passable_edges_as_b",
                    ),
                ),
                to_attr="positions_cached",
            ),
            Prefetch(
                "participants",
                queryset=CombatParticipant.objects.select_related(
                    "character_sheet__character",
                    "character_sheet__character__object_position__position",
                    "character_sheet__vitals",
                    "character_sheet__fatigue",
                    "covenant_role",
                )
                .filter(status=ParticipantStatus.ACTIVE)
                .prefetch_related(
                    self._active_conditions_prefetch("character_sheet__character"),
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
                ).prefetch_related(
                    self._active_conditions_prefetch("objectdb"),
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
        if getattr(user, "is_staff", False):  # noqa: GETATTR_LITERAL
            return qs
        return qs.filter(scene__in=Scene.objects.viewable_by(user)).distinct()

    # --- GM Lifecycle Actions ---

    @action(detail=True, methods=[HTTPMethod.POST])
    def begin_round(self, request: Request, pk: int | None = None) -> Response:
        """Begin a new declaration phase."""
        encounter = self.get_object()
        try:
            begin_declaration_phase(encounter)
        except ValueError:
            return Response(
                {"detail": _ERR_INVALID_STATUS},
                status=status.HTTP_400_BAD_REQUEST,
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
        except Exception:  # noqa: BLE001
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
        new_opponent = add_opponent(
            encounter,
            name=data["name"],
            tier=data["tier"],
            max_health=data.get("max_health"),
            threat_pool=pool,
            description=data.get("description", ""),
            soak_value=data.get("soak_value", 0),
            probing_threshold=data.get("probing_threshold"),
            position=position,
        )
        # Update cached opponent list in-place
        encounter.opponents_cached.append(new_opponent)
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

    @action(detail=True, methods=[HTTPMethod.GET])
    def available_combos(
        self,
        request: Request,
        pk: int | None = None,
    ) -> Response:
        """Get available combos for the current round."""
        encounter = self.get_object()
        combos = run_combo_detection(encounter, encounter.round_number)
        data = [
            {
                "combo_id": c.combo.pk,
                "combo_name": c.combo.name,
                "known_by_participant": c.known_by_participant,
                "slot_count": len(c.slot_matches),
            }
            for c in combos
        ]
        return Response(data)

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
