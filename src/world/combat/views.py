"""ViewSet for combat encounter management."""

from __future__ import annotations

from http import HTTPMethod
from typing import cast

from django.db.models import Prefetch, QuerySet
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from evennia.accounts.models import AccountDB
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import Serializer
from rest_framework.viewsets import ModelViewSet

from world.character_sheets.models import CharacterSheet
from world.combat.constants import ParticipantStatus
from world.combat.filters import CombatEncounterFilter
from world.combat.models import (
    CombatEncounter,
    CombatOpponent,
    CombatParticipant,
    CombatRoundAction,
    ComboDefinition,
    ThreatPool,
)
from world.combat.permissions import (
    IsEncounterGMOrStaff,
    IsEncounterParticipant,
    IsInEncounterRoom,
)
from world.combat.serializers import (
    AddOpponentSerializer,
    AddParticipantSerializer,
    DeclareActionSerializer,
    EncounterDetailSerializer,
    EncounterListSerializer,
    RemoveParticipantSerializer,
    RoundActionSerializer,
    UpgradeComboSerializer,
)
from world.combat.services import (
    add_opponent,
    add_participant,
    begin_declaration_phase,
    declare_action,
    declare_flee,
    join_encounter,
    resolve_round,
    revert_combo_upgrade,
    run_combo_detection,
    upgrade_action_to_combo,
)
from world.covenants.models import CovenantRole
from world.magic.models import Technique
from world.roster.models import RosterEntry
from world.stories.pagination import StandardResultsSetPagination

# Fixed error messages for API responses (never expose raw exception strings).
_ERR_NOT_PARTICIPANT = "Not a participant in this encounter."
_ERR_NO_ACTION = "No action declared for this round."
_ERR_ALREADY_JOINED = "Already in this encounter."
_ERR_NO_CHARACTER = "No active character found."
_ERR_ADD_PARTICIPANT = "Failed to add participant."
_ERR_DECLARE_FAILED = "Failed to declare action."
_ERR_INVALID_STATUS = "Encounter is not in a valid status for this action."
_ERR_COMBO_UPGRADE = "Cannot upgrade to the requested combo."


class CombatEncounterViewSet(ModelViewSet):
    """ViewSet for combat encounter lifecycle and player actions."""

    filter_backends = [DjangoFilterBackend]
    filterset_class = CombatEncounterFilter
    pagination_class = StandardResultsSetPagination

    def get_permissions(self) -> list:
        if self.action in ("list", "retrieve"):
            return [IsAuthenticated()]
        if self.action in (
            "declare",
            "ready",
            "my_action",
            "available_combos",
            "upgrade_combo",
            "revert_combo",
            "flee",
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

    def _base_queryset(self) -> QuerySet[CombatEncounter]:
        return CombatEncounter.objects.select_related("scene").prefetch_related(
            Prefetch(
                "participants",
                queryset=CombatParticipant.objects.select_related(
                    "character_sheet__character",
                    "character_sheet__vitals",
                    "covenant_role",
                ).filter(status=ParticipantStatus.ACTIVE),
                to_attr="participants_cached",
            ),
            Prefetch(
                "opponents",
                queryset=CombatOpponent.objects.all(),
                to_attr="opponents_cached",
            ),
        )

    def get_queryset(self) -> QuerySet[CombatEncounter]:
        return self._base_queryset().order_by("-created_at")

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
        encounter.refresh_from_db()
        return self._detail_response(request, encounter)

    @action(detail=True, methods=[HTTPMethod.POST])
    def resolve_round(self, request: Request, pk: int | None = None) -> Response:
        """Resolve the current round."""
        encounter = self.get_object()
        try:
            resolve_round(encounter)
        except ValueError:
            return Response(
                {"detail": _ERR_INVALID_STATUS},
                status=status.HTTP_400_BAD_REQUEST,
            )
        encounter.refresh_from_db()
        return self._detail_response(request, encounter)

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
            add_participant(encounter, sheet, covenant_role=covenant_role)
        except Exception:  # noqa: BLE001
            return Response(
                {"detail": _ERR_ADD_PARTICIPANT},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return self._detail_response(request, encounter)

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
        participant.status = ParticipantStatus.REMOVED
        participant.save(update_fields=["status"])
        return self._detail_response(request, encounter)

    @action(detail=True, methods=[HTTPMethod.POST])
    def add_opponent(self, request: Request, pk: int | None = None) -> Response:
        """Add an NPC opponent to the encounter (GM action)."""
        encounter = self.get_object()
        serializer = AddOpponentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        pool = get_object_or_404(ThreatPool, pk=data["threat_pool_id"])
        add_opponent(
            encounter,
            name=data["name"],
            tier=data["tier"],
            max_health=data["max_health"],
            threat_pool=pool,
            description=data.get("description", ""),
            soak_value=data.get("soak_value", 0),
            probing_threshold=data.get("probing_threshold"),
        )
        return self._detail_response(request, encounter)

    @action(detail=True, methods=[HTTPMethod.POST])
    def pause(self, request: Request, pk: int | None = None) -> Response:
        """Pause or unpause the encounter timer."""
        encounter = self.get_object()
        encounter.is_paused = not encounter.is_paused
        encounter.save(update_fields=["is_paused"])
        return self._detail_response(request, encounter)

    # --- Player Actions ---

    @action(detail=True, methods=[HTTPMethod.POST])
    def declare(self, request: Request, pk: int | None = None) -> Response:
        """Declare actions for the current round."""
        encounter = self.get_object()
        serializer = DeclareActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        participant = self._get_participant(request, encounter)
        if not participant:
            return Response(
                {"detail": _ERR_NOT_PARTICIPANT},
                status=status.HTTP_403_FORBIDDEN,
            )
        data = serializer.validated_data

        # Resolve focused action FK
        focused_action = None
        focused_action_id = data.get("focused_action")
        if focused_action_id:
            focused_action = get_object_or_404(Technique, pk=focused_action_id)

        # Resolve focused target FK
        focused_target = None
        target_id = data.get("focused_target")
        if target_id:
            focused_target = get_object_or_404(
                CombatOpponent,
                pk=target_id,
                encounter=encounter,
            )

        # Resolve passive technique FKs
        passive_kwargs: dict[str, Technique | None] = {}
        for passive_field in ("physical_passive", "social_passive", "mental_passive"):
            passive_id = data.get(passive_field)
            if passive_id:
                passive_kwargs[passive_field] = get_object_or_404(
                    Technique,
                    pk=passive_id,
                )

        try:
            declare_action(
                participant,
                focused_action=focused_action,
                focused_category=data.get("focused_category"),
                effort_level=data["effort_level"],
                focused_target=focused_target,
                **passive_kwargs,
            )
        except ValueError:
            return Response(
                {"detail": _ERR_DECLARE_FAILED},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return self._detail_response(request, encounter)

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
        current_action = CombatRoundAction.objects.filter(
            participant=participant,
            round_number=encounter.round_number,
        ).first()
        if not current_action:
            return Response(
                {"detail": _ERR_NO_ACTION},
                status=status.HTTP_400_BAD_REQUEST,
            )
        current_action.is_ready = not current_action.is_ready
        current_action.save(update_fields=["is_ready"])
        return self._detail_response(request, encounter)

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
        action_obj = CombatRoundAction.objects.filter(
            participant=participant,
            round_number=encounter.round_number,
        ).first()
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
        combo = get_object_or_404(ComboDefinition, pk=combo_id)
        current_action = CombatRoundAction.objects.filter(
            participant=participant,
            round_number=encounter.round_number,
        ).first()
        if not current_action:
            return Response(
                {"detail": _ERR_NO_ACTION},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            upgrade_action_to_combo(current_action, combo)
        except ValueError:
            return Response(
                {"detail": _ERR_COMBO_UPGRADE},
                status=status.HTTP_400_BAD_REQUEST,
            )
        current_action.is_ready = False
        current_action.save(update_fields=["is_ready"])
        return self._detail_response(request, encounter)

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
        current_action = CombatRoundAction.objects.filter(
            participant=participant,
            round_number=encounter.round_number,
        ).first()
        if not current_action:
            return Response(
                {"detail": _ERR_NO_ACTION},
                status=status.HTTP_400_BAD_REQUEST,
            )
        revert_combo_upgrade(current_action)
        current_action.is_ready = False
        current_action.save(update_fields=["is_ready"])
        return self._detail_response(request, encounter)

    # --- Participation ---

    @action(detail=True, methods=[HTTPMethod.POST])
    def join(self, request: Request, pk: int | None = None) -> Response:
        """Player self-joins the encounter."""
        encounter = self.get_object()
        user = cast(AccountDB, request.user)
        active_entries = RosterEntry.objects.for_account(user)
        character_ids = active_entries.values_list("character_id", flat=True)
        sheet = CharacterSheet.objects.filter(character_id__in=character_ids).first()
        if not sheet:
            return Response(
                {"detail": _ERR_NO_CHARACTER},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            join_encounter(encounter, sheet)
        except ValueError:
            return Response(
                {"detail": _ERR_ALREADY_JOINED},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return self._detail_response(request, encounter)

    @action(detail=True, methods=[HTTPMethod.POST])
    def flee(self, request: Request, pk: int | None = None) -> Response:
        """Declare intent to flee. Creates a passives-only action."""
        encounter = self.get_object()
        participant = self._get_participant(request, encounter)
        if not participant:
            return Response(
                {"detail": _ERR_NOT_PARTICIPANT},
                status=status.HTTP_403_FORBIDDEN,
            )
        declare_flee(participant)
        return self._detail_response(request, encounter)

    # --- Helpers ---

    def _detail_response(
        self,
        request: Request,
        encounter: CombatEncounter,
    ) -> Response:
        """Return encounter detail, refreshing caches after mutations.

        Flushes the SharedMemoryModel cache for the encounter so
        participants_cached and opponents_cached are re-populated,
        then serializes with pre-computed viewer context.
        """
        encounter.flush_from_cache(force=True)
        refreshed = self._base_queryset().get(pk=encounter.pk)
        context = self._build_serializer_context(request, refreshed)
        return Response(
            EncounterDetailSerializer(refreshed, context=context).data,
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

        if not request.user.is_authenticated:
            context["viewer_character_ids"] = set()
            context["is_gm"] = False
            return context

        user = cast(AccountDB, request.user)
        character_ids = set(
            RosterEntry.objects.for_account(user).character_ids(),
        )
        context["viewer_character_ids"] = character_ids

        is_gm = False
        if not request.user.is_staff and encounter.scene:
            is_gm = encounter.scene.is_gm(request.user)
        context["is_gm"] = request.user.is_staff or is_gm

        return context

    def _get_participant(
        self,
        request: Request,
        encounter: CombatEncounter,
    ) -> CombatParticipant | None:
        """Get the requesting user's active participant from cached data.

        Uses participants_cached (prefetched on the encounter) and
        viewer_character_ids (from serializer context or fresh lookup).
        No DB query if the encounter was loaded via _base_queryset.
        """
        user = cast(AccountDB, request.user)
        character_ids = set(
            RosterEntry.objects.for_account(user).character_ids(),
        )
        try:
            participants = encounter.participants_cached
        except AttributeError:
            # Fallback if encounter wasn't loaded via _base_queryset
            return CombatParticipant.objects.filter(
                encounter=encounter,
                character_sheet__character_id__in=character_ids,
                status=ParticipantStatus.ACTIVE,
            ).first()
        return next(
            (p for p in participants if p.character_sheet.character_id in character_ids),
            None,
        )
