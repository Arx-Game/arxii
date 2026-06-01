"""
API views for the magic system.

This module provides ViewSets for:
- Lookup tables (read-only): TechniqueStyle, EffectType, Restriction, Facet
- CG CRUD: Gift, Technique
- Character magic data: Aura, Gifts, Anima, Rituals
- Spec A §4.5 surface: Thread, Ritual perform, Thread pull preview,
  ThreadWeavingTeachingOffer
"""

import dataclasses
from dataclasses import asdict
from typing import cast

from django.db.models import Count, F, Prefetch
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from evennia.accounts.models import AccountDB
from evennia.objects.models import ObjectDB
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.mixins import ListModelMixin, RetrieveModelMixin
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet

from world.character_sheets.models import CharacterSheet
from world.magic.constants import PendingAlterationStatus, RitualExecutionKind
from world.magic.exceptions import (
    AnchorCapExceeded,
    InvalidImbueAmount,
    ResonanceInsufficient,
    RitualComponentError,
    XPInsufficient,
)
from world.magic.filters import (
    CantripFilter,
    CharacterAnimaFilter,
    CharacterAuraFilter,
    CharacterGiftFilter,
    CharacterResonanceFilter,
    ResonanceGrantFilterSet,
    RitualSessionFilterSet,
    ThreadFilter,
    ThreadWeavingTeachingOfferFilter,
)
from world.magic.models import (
    Cantrip,
    CharacterAnima,
    CharacterAura,
    CharacterGift,
    CharacterResonance,
    EffectType,
    Facet,
    Gift,
    MagicalAlterationTemplate,
    PendingAlteration,
    PoseEndorsement,
    Resonance,
    ResonanceGrant,
    Restriction,
    Ritual,
    SceneEntryEndorsement,
    Technique,
    TechniqueStyle,
    Thread,
    ThreadWeavingTeachingOffer,
)
from world.magic.permissions import IsRitualAuthorOrStaff, IsThreadOwner
from world.magic.serializers import (
    AcceptTeachingOfferResponseSerializer,
    AcceptTeachingOfferSerializer,
    AlterationResolutionSerializer,
    ApplicablePullsRequestSerializer,
    CantripSerializer,
    CharacterAnimaSerializer,
    CharacterAuraSerializer,
    CharacterGiftSerializer,
    CharacterResonanceSerializer,
    CrossXPLockResponseSerializer,
    CrossXPLockSerializer,
    EffectTypeSerializer,
    FacetSerializer,
    FacetTreeSerializer,
    GiftCreateSerializer,
    GiftListSerializer,
    GiftSerializer,
    LibraryEntrySerializer,
    PendingAlterationSerializer,
    PoseEndorsementSerializer,
    ResonanceGrantSerializer,
    RestrictionSerializer,
    RitualPatchSerializer,
    RitualPerformRequestSerializer,
    RitualSerializer,
    RitualSessionDetailSerializer,
    RitualSessionDraftSerializer,
    RoomBriefSerializer,
    SceneEntryEndorsementSerializer,
    TechniqueSerializer,
    TechniqueStyleSerializer,
    ThreadApplicabilitySerializer,
    ThreadHubSummarySerializer,
    ThreadPullCommitRequestSerializer,
    ThreadPullCommitResponseSerializer,
    ThreadPullPreviewRequestSerializer,
    ThreadPullPreviewResponseSerializer,
    ThreadSerializer,
    ThreadWeavingTeachingOfferSerializer,
)
from world.magic.services import (
    get_library_entries,
    preview_resonance_pull,
    resolve_pending_alteration,
)
from world.magic.services.auth import _resolve_actor_sheet, _resolve_endorser_sheet
from world.magic.services.gain import account_for_sheet
from world.magic.services.pull_applicability import PullActionContext, compute_thread_applicability
from world.roster.models import RosterEntry
from world.stories.pagination import StandardResultsSetPagination

# Error messages — module constants keep tests stable and satisfy STRING_LITERAL.
_ERR_THREAD_NOT_FOUND = "Thread not found or not owned by the actor."
_ERR_RESONANCE_NOT_FOUND = "Resonance not found."
_ERR_IMBUING_REQUIRES_THREAD = "Imbuing ritual requires thread_id in kwargs (int)."
_IMBUING_SERVICE_PATH = "world.magic.services.spend_resonance_for_imbuing"

# =============================================================================
# Lookup Table ViewSets (Read-Only)
# =============================================================================


class TechniqueStyleViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for TechniqueStyle lookup records.

    Provides read-only access to technique styles (Manifestation, Subtle, etc.).
    """

    # Use Prefetch with to_attr for SharedMemoryModel to avoid cache pollution
    queryset = TechniqueStyle.objects.prefetch_related(
        Prefetch("allowed_paths", to_attr="cached_allowed_paths")
    )
    serializer_class = TechniqueStyleSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None  # Small lookup table


class EffectTypeViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for EffectType lookup records.

    Provides read-only access to effect types (Attack, Defense, Movement, etc.).
    """

    queryset = EffectType.objects.all()
    serializer_class = EffectTypeSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None  # Small lookup table


class RestrictionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for Restriction lookup records.

    Provides read-only access to restrictions that grant power bonuses.
    """

    # Use Prefetch with to_attr for SharedMemoryModel to avoid cache pollution
    queryset = Restriction.objects.prefetch_related(
        Prefetch("allowed_effect_types", to_attr="cached_allowed_effect_types")
    )
    serializer_class = RestrictionSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["allowed_effect_types"]
    pagination_class = None  # Small lookup table


class CantripViewSet(viewsets.ReadOnlyModelViewSet):
    """
    List active cantrips for character creation.

    Returns all active cantrips with their allowed facets.
    Accepts optional ``?path_id=<int>`` to filter by Path's allowed styles.
    Registered under /api/character-creation/ since it's used during CG.
    """

    serializer_class = CantripSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None  # Small lookup table
    filter_backends = [DjangoFilterBackend]
    filterset_class = CantripFilter

    def get_queryset(self):
        """Return active cantrips with prefetched allowed facets."""
        return Cantrip.objects.filter(is_active=True).prefetch_related(
            Prefetch(
                "allowed_facets",
                queryset=Facet.objects.all(),
                to_attr="cached_allowed_facets",
            )
        )


class FacetViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for Facet records.

    Provides read-only access to the facet hierarchy.
    Use ?parent=<id> to filter by parent, or ?parent__isnull=true for top-level.
    """

    queryset = Facet.objects.select_related("parent").order_by("name")
    serializer_class = FacetSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = {"parent": ["exact", "isnull"]}
    search_fields = ["name", "description"]
    pagination_class = None  # Facets are browsed as tree

    def get_serializer_class(self):
        """Use tree serializer for tree action."""
        if self.action == "tree":
            return FacetTreeSerializer
        return FacetSerializer

    @action(detail=False, methods=["get"])
    def tree(self, request):
        """Return facets as nested tree structure."""
        # Only top-level facets, children are nested by serializer.
        # Bounded recursive prefetch (3 levels deep) — kept as bare string because
        # nested Prefetch objects for self-referencing tree traversal are unwieldy
        # and the depth is explicitly bounded.
        _children_prefetch = "children__children__children"
        top_level = Facet.objects.filter(parent__isnull=True).prefetch_related(_children_prefetch)
        serializer = FacetTreeSerializer(top_level, many=True)
        return Response(serializer.data)


class GiftViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Gift records.

    Provides CRUD access to magical gift definitions for character creation.
    Note: technique_count is annotated to avoid N+1 queries in serializer.
    """

    # Use Prefetch with to_attr for SharedMemoryModel to avoid cache pollution
    queryset = (
        Gift.objects.prefetch_related(
            Prefetch(
                "resonances",
                queryset=Resonance.objects.select_related(
                    "affinity", "modifier_target__codex_entry"
                ),
                to_attr="cached_resonances",
            ),
            Prefetch(
                "techniques",
                queryset=Technique.objects.select_related("style", "effect_type"),
                to_attr="cached_techniques",
            ),
        )
        .annotate(technique_count=Count("techniques"))
        .order_by("name")
    )
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_serializer_class(self):
        """Use create serializer for write ops, list/detail serializers for reads."""
        if self.action in ["create", "update", "partial_update"]:
            return GiftCreateSerializer
        if self.action == "list":
            return GiftListSerializer
        return GiftSerializer


class TechniqueViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Technique records.

    Provides CRUD access to techniques for character creation.
    """

    queryset = (
        Technique.objects.select_related("gift", "style", "effect_type")
        .prefetch_related(
            Prefetch(
                "restrictions",
                queryset=Restriction.objects.all(),
                to_attr="cached_restrictions",
            ),
        )
        .order_by("name")
    )
    serializer_class = TechniqueSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ["gift", "style", "effect_type"]
    ordering_fields = ["name", "level"]
    pagination_class = StandardResultsSetPagination


# =============================================================================
# Character Magic ViewSets
# =============================================================================


class CharacterAuraViewSet(viewsets.ModelViewSet):
    """
    ViewSet for CharacterAura records.

    Provides access to character aura data. Non-staff users see all
    characters they currently play (active roster tenure), regardless
    of whether they are actively puppeting them right now. Frontends
    that need a single-character view should pass ``?character=<pk>``
    to disambiguate when the user has alts.
    """

    serializer_class = CharacterAuraSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = CharacterAuraFilter

    def get_queryset(self):
        """Filter to characters the current user plays (or all if staff)."""
        user = self.request.user
        if user.is_staff:
            return CharacterAura.objects.all()
        character_ids = RosterEntry.objects.for_account(cast(AccountDB, user)).character_ids()
        return CharacterAura.objects.filter(character_id__in=character_ids)


class CharacterResonanceViewSet(viewsets.ModelViewSet):
    """
    ViewSet for CharacterResonance records.

    Manages personal resonances attached to characters. Non-staff users
    see all characters they currently play (active roster tenure),
    regardless of whether they are actively puppeting them right now.
    Frontends that operate on a single character (e.g., the resonance
    picker for rituals) should pass ``?character_sheet=<pk>`` so the
    result is unambiguous when the user has alts.
    """

    serializer_class = CharacterResonanceSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = CharacterResonanceFilter

    def get_queryset(self):
        """Filter to characters the current user plays (or all if staff)."""
        user = self.request.user
        queryset = CharacterResonance.objects.select_related(
            "character_sheet",
            "character_sheet__character",
            "resonance",
            "resonance__affinity",
            "resonance__modifier_target__codex_entry",
        )
        if user.is_staff:
            return queryset
        sheet_ids = RosterEntry.objects.for_account(cast(AccountDB, user)).character_ids()
        return queryset.filter(character_sheet_id__in=sheet_ids)


class CharacterGiftViewSet(viewsets.ModelViewSet):
    """
    ViewSet for CharacterGift records.

    Manages gifts possessed by characters. Non-staff users see all
    characters they currently play (active roster tenure), regardless
    of whether they are actively puppeting them right now. Pass
    ``?character=<pk>`` to narrow to a single character.
    """

    serializer_class = CharacterGiftSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = CharacterGiftFilter

    def get_queryset(self):
        """Filter to characters the current user plays (or all if staff)."""
        user = self.request.user
        queryset = CharacterGift.objects.select_related("gift").prefetch_related(
            Prefetch(
                "gift__resonances",
                queryset=Resonance.objects.select_related(
                    "affinity", "modifier_target__codex_entry"
                ),
                to_attr="cached_resonances",
            ),
            Prefetch(
                "gift__techniques",
                queryset=Technique.objects.select_related("style", "effect_type"),
                to_attr="cached_techniques",
            ),
        )
        if user.is_staff:
            return queryset
        character_ids = RosterEntry.objects.for_account(cast(AccountDB, user)).character_ids()
        return queryset.filter(character_id__in=character_ids)


class CharacterAnimaViewSet(viewsets.ModelViewSet):
    """
    ViewSet for CharacterAnima records.

    Manages character anima (magical energy) tracking. Non-staff users
    see all characters they currently play (active roster tenure),
    regardless of whether they are actively puppeting them right now.
    Pass ``?character=<pk>`` to narrow to a single character.
    """

    serializer_class = CharacterAnimaSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = CharacterAnimaFilter

    def get_queryset(self):
        """Filter to characters the current user plays (or all if staff)."""
        user = self.request.user
        if user.is_staff:
            return CharacterAnima.objects.all()
        character_ids = RosterEntry.objects.for_account(cast(AccountDB, user)).character_ids()
        return CharacterAnima.objects.filter(character_id__in=character_ids)


# =============================================================================
# Alteration ViewSets
# =============================================================================


class PendingAlterationViewSet(
    ListModelMixin,
    RetrieveModelMixin,
    GenericViewSet,
):
    """ViewSet for pending Mage Scars.

    list: Returns the authenticated player's open pending alterations.
    retrieve: Returns a single pending alteration.
    resolve: Custom action to resolve a pending via author or library path.
    library: Custom action to browse tier-matched library entries.
    """

    serializer_class = PendingAlterationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["status", "tier"]

    def get_queryset(self):
        """Filter to pending alterations for characters owned by the current user.

        Defaults to status=OPEN when no ?status= query param is supplied. Clients may
        pass ?status=resolved (or any other value) to see non-open rows; django-filter
        then applies the explicit status filter on top of the base ownership queryset.
        """
        qs = (
            PendingAlteration.objects.filter(
                character__character__db_account=self.request.user,
            )
            .select_related(
                "origin_affinity",
                "origin_resonance",
                "triggering_scene",
            )
            .order_by("-pk")
        )
        # Apply OPEN default only when the client has not explicitly requested a status.
        if "status" not in self.request.query_params:  # noqa: STRING_LITERAL — HTTP param name
            qs = qs.filter(status=PendingAlterationStatus.OPEN)
        return qs

    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        """Resolve a pending alteration via author-from-scratch or library path."""
        pending = self.get_object()
        serializer = AlterationResolutionSerializer(
            data=request.data,
            context={
                "pending": pending,
                "request": request,
                "character_sheet": pending.character,
            },
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        library_template = data.get("library_template_id")  # PrimaryKeyRelatedField → instance
        if library_template is not None:
            # Re-fetch with select_related to ensure condition_template is loaded.
            library_template = MagicalAlterationTemplate.objects.select_related(
                "condition_template"
            ).get(pk=library_template.pk)
            result = resolve_pending_alteration(
                pending=pending,
                name=library_template.condition_template.name,
                player_description=library_template.condition_template.player_description,
                observer_description=library_template.condition_template.observer_description,
                weakness_magnitude=library_template.weakness_magnitude,
                resonance_bonus_magnitude=library_template.resonance_bonus_magnitude,
                social_reactivity_magnitude=library_template.social_reactivity_magnitude,
                is_visible_at_rest=library_template.is_visible_at_rest,
                resolved_by=request.user,
                library_template=library_template,
            )
        else:
            # weakness_damage_type_id and parent_template_id are PrimaryKeyRelatedField →
            # validated_data holds instances (or None), no extra .objects.get() needed.
            weakness_dt = data.get("weakness_damage_type_id")
            parent = data.get("parent_template_id")

            result = resolve_pending_alteration(
                pending=pending,
                name=data["name"],
                player_description=data["player_description"],
                observer_description=data["observer_description"],
                weakness_damage_type=weakness_dt,
                weakness_magnitude=data.get("weakness_magnitude", 0),
                resonance_bonus_magnitude=data.get("resonance_bonus_magnitude", 0),
                social_reactivity_magnitude=data.get("social_reactivity_magnitude", 0),
                is_visible_at_rest=data.get("is_visible_at_rest", False),
                resolved_by=request.user,
                parent_template=parent,
            )

        return Response(
            {"status": "resolved", "event_id": result.event.pk},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["get"])
    def library(self, request, pk=None):
        """Browse tier-matched library entries for a pending alteration."""
        pending = self.get_object()
        entries = get_library_entries(
            tier=pending.tier,
            character_affinity_id=pending.origin_affinity_id,
        )
        serializer = LibraryEntrySerializer(entries, many=True)
        return Response(serializer.data)


# =============================================================================
# Resonance Pivot Spec A — Phase 16 API surface (§4.5, §5.6)
# =============================================================================


class ThreadViewSet(viewsets.ModelViewSet):
    """ViewSet for Thread records (Spec A §4.5).

    list / retrieve: returns threads the requesting account owns (staff can
    see all), excluding soft-retired rows.
    create: delegates to the serializer, which calls ``weave_thread``. The
    caller MUST supply ``character_sheet_id`` identifying which owned sheet
    to weave the thread for — no implicit first-sheet selection.
    destroy: soft-retire — sets ``retired_at`` rather than deleting the row,
    so historical references remain.
    """

    serializer_class = ThreadSerializer
    permission_classes = [IsAuthenticated, IsThreadOwner]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = ThreadFilter

    def get_queryset(self):
        """Filter to threads owned by the requesting account; exclude retired."""
        user = self.request.user
        qs = (
            Thread.objects.filter(retired_at__isnull=True)
            .select_related(
                "owner",
                "owner__character",
                "resonance",
                "resonance__affinity",
                "target_trait",
                "target_technique",
                "target_object",
                "target_relationship_track",
                "target_capstone",
            )
            .order_by("-pk")
        )
        if user.is_staff:
            return qs
        character_ids = RosterEntry.objects.for_account(
            cast(AccountDB, user),
        ).character_ids()
        return qs.filter(owner_id__in=character_ids)

    def destroy(self, request: Request, *args, **kwargs) -> Response:
        """Soft-retire the thread by stamping ``retired_at`` instead of deleting.

        Spec A §4.5: DELETE is a soft-retire — retired threads stop appearing
        in list/detail, never contribute to pulls or passives, but remain
        intact so historical journal references keep resolving.
        """
        thread = self.get_object()
        thread.retired_at = timezone.now()
        thread.save(update_fields=["retired_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        request=CrossXPLockSerializer,
        responses={200: CrossXPLockResponseSerializer},
    )
    @action(detail=True, methods=["post"])
    def cross_xp_lock(self, request: Request, pk: int | None = None) -> Response:
        """Pay XP to unlock the next level boundary on this thread (Spec A §3.2).

        POST /api/magic/threads/{id}/cross-xp-lock/

        Request body: ``{boundary_level}`` — the XP-locked boundary level to unlock.
        Response: ``{thread_id, unlocked_level, xp_spent}``.
        Idempotent: repeat calls with the same boundary_level return the existing
        ThreadLevelUnlock without re-spending XP.
        """
        thread = self.get_object()
        serializer = CrossXPLockSerializer(
            data=request.data,
            context={"request": request, "thread": thread},
        )
        serializer.is_valid(raise_exception=True)
        unlock = serializer.save()
        return Response(
            {
                "thread_id": thread.pk,
                "unlocked_level": unlock.unlocked_level,
                "xp_spent": unlock.xp_spent,
            },
            status=status.HTTP_200_OK,
        )


class ThreadPullPreviewView(APIView):
    """Read-only preview of a resonance pull (Spec A §5.6).

    POST /api/magic/thread-pull-preview/

    Request body: ``{resonance_id, tier, thread_ids[], action_context?}``.
    Response: ``{resonance_cost, anima_cost, affordable, resolved_effects[],
    capped_intensity}``. Never mutates state.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=ThreadPullPreviewRequestSerializer,
        responses={200: ThreadPullPreviewResponseSerializer},
    )
    def post(self, request: Request) -> Response:
        """Run the preview and return its wire representation."""
        serializer = ThreadPullPreviewRequestSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        sheet: CharacterSheet = data["character_sheet_id"]

        resonance = get_object_or_404(Resonance, pk=data["resonance_id"])

        thread_ids: list[int] = data["thread_ids"]
        threads = list(
            Thread.objects.filter(
                pk__in=thread_ids,
                owner=sheet,
                retired_at__isnull=True,
            ).select_related("resonance", "owner")
        )
        if len(threads) != len(thread_ids):
            return Response(
                {"detail": _ERR_THREAD_NOT_FOUND},
                status=status.HTTP_400_BAD_REQUEST,
            )

        combat_encounter = None
        action_ctx = data.get("action_context") or {}
        encounter_id = action_ctx.get("combat_encounter_id") if action_ctx else None
        if encounter_id:
            from world.combat.models import CombatEncounter  # noqa: PLC0415

            combat_encounter = get_object_or_404(CombatEncounter, pk=encounter_id)

        try:
            result = preview_resonance_pull(
                character_sheet=sheet,
                resonance=resonance,
                tier=data["tier"],
                threads=threads,
                combat_encounter=combat_encounter,
            )
        except InvalidImbueAmount as exc:
            return Response(
                {"detail": exc.user_message},
                status=status.HTTP_400_BAD_REQUEST,
            )

        response_serializer = ThreadPullPreviewResponseSerializer(result)
        return Response(response_serializer.data)


class ThreadPullCommitView(APIView):
    """Atomic commit of a resonance pull (Spec A §5.4 + §7.4).

    POST /api/magic/thread-pull-commit/

    Request body: ``{character_sheet_id, resonance_id, tier, thread_ids[],
    action_context?}``.  The ``action_context`` dict may carry
    ``combat_encounter_id`` + ``combat_participant_id`` (combat mode) or be
    absent / empty (ephemeral mode).

    Response: ``{resonance_spent, anima_spent, resolved_effects[]}``.
    Mutates state: debits resonance + anima, and — in combat mode — persists a
    ``CombatPull`` row with ``CombatPullResolvedEffect`` snapshots.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=ThreadPullCommitRequestSerializer,
        responses={200: ThreadPullCommitResponseSerializer},
    )
    def post(self, request: Request) -> Response:
        """Dispatch the pull and return the commit result."""
        serializer = ThreadPullCommitRequestSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        return Response(
            ThreadPullCommitResponseSerializer(result).data,
            status=status.HTTP_200_OK,
        )


class RitualViewSet(viewsets.ModelViewSet):
    """ViewSet exposing authored Rituals with author-restricted PATCH.

    Used by the frontend to discover available rituals and their `input_schema`
    for rendering the perform form. The actual dispatch happens through
    `RitualPerformView` at `POST /api/magic/rituals/perform/`.

    PATCH is restricted to the Ritual's author or staff. DELETE is disabled
    (rituals are not deleted via API — staff can remove from admin).
    """

    queryset = Ritual.objects.select_related("scene_action_config").order_by("name")
    permission_classes = [IsAuthenticated, IsRitualAuthorOrStaff]
    pagination_class = StandardResultsSetPagination
    http_method_names = ["get", "patch", "head", "options"]

    def get_serializer_class(self):
        """Use write serializer for PATCH, read serializer otherwise."""
        if self.action == "partial_update":
            return RitualPatchSerializer
        return RitualSerializer


class RitualPerformView(APIView):
    """Dispatch a Ritual via PerformRitualAction (Spec A §4.5).

    POST /api/magic/rituals/perform/

    Accepts ``{ritual_id, kwargs, components[]}``; ``kwargs`` values are
    restricted to primitives by the serializer. For SERVICE rituals that
    take model instances (Imbuing takes a Thread), the view resolves the
    primitive key (``thread_id``) into the live model instance before
    invoking ``PerformRitualAction``. Service-level typed exceptions carry
    ``user_message`` and are mapped to HTTP 400.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        """Validate, resolve, and dispatch the ritual; return a result payload."""
        serializer = RitualPerformRequestSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        sheet: CharacterSheet = data["character_sheet_id"]

        ritual = data["ritual_id"]
        kwargs: dict = dict(data.get("kwargs") or {})
        components = list(data.get("components") or [])

        # Imbuing (and potentially other SERVICE rituals) takes a Thread. The
        # primitive-only kwargs surface carries ``thread_id``; resolve here.
        if ritual.service_function_path == _IMBUING_SERVICE_PATH:
            thread_id = kwargs.pop("thread_id", None)
            if not isinstance(thread_id, int):
                return Response(
                    {"detail": _ERR_IMBUING_REQUIRES_THREAD},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            thread = Thread.objects.filter(
                pk=thread_id,
                owner=sheet,
                retired_at__isnull=True,
            ).first()
            if thread is None:
                return Response(
                    {"detail": _ERR_THREAD_NOT_FOUND},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            kwargs["thread"] = thread

        from world.magic.actions import PerformRitualAction  # noqa: PLC0415

        action_obj = PerformRitualAction(
            actor=sheet,
            ritual=ritual,
            components_provided=components,
            kwargs=kwargs,
        )
        try:
            result = action_obj.execute()
        except (
            RitualComponentError,
            ResonanceInsufficient,
            AnchorCapExceeded,
            InvalidImbueAmount,
            XPInsufficient,
        ) as exc:
            return Response(
                {"detail": exc.user_message},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payload: dict = {
            "ritual_id": ritual.pk,
            "execution_kind": ritual.execution_kind,
        }
        if ritual.execution_kind == RitualExecutionKind.SERVICE and result is not None:
            payload["result"] = asdict(result) if dataclasses.is_dataclass(result) else result
        return Response(payload, status=status.HTTP_200_OK)


class ThreadWeavingTeachingOfferViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only ViewSet for ThreadWeavingTeachingOffer records (Spec A §4.5)."""

    queryset = ThreadWeavingTeachingOffer.objects.select_related(
        "teacher",
        # FK chain consumed by ThreadWeavingTeachingOfferSerializer.teacher_display_name
        # (RosterTenure.display_name walks roster_entry → character_sheet → character).
        "teacher__roster_entry__character_sheet__character",
        "unlock",
        "unlock__unlock_trait",
        "unlock__unlock_gift",
        "unlock__unlock_room_property",
        "unlock__unlock_track",
    ).order_by("-pk")
    serializer_class = ThreadWeavingTeachingOfferSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = ThreadWeavingTeachingOfferFilter

    @extend_schema(
        request=AcceptTeachingOfferSerializer,
        responses={201: AcceptTeachingOfferResponseSerializer},
    )
    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def accept(self, request: Request, pk: int | None = None) -> Response:
        """Accept a ThreadWeavingTeachingOffer on behalf of the requesting learner.

        POST /api/magic/teaching-offers/{id}/accept/

        The requesting account must have at least one active tenure.  If the
        account has multiple active tenures the body must include
        ``learner_sheet_id`` to identify which character is learning.
        """
        offer = self.get_object()
        serializer = AcceptTeachingOfferSerializer(
            data=request.data,
            context={"request": request, "offer": offer},
        )
        serializer.is_valid(raise_exception=True)
        char_unlock = serializer.save()
        return Response(
            {
                "id": char_unlock.pk,
                "unlock_id": char_unlock.unlock_id,
                "xp_spent": char_unlock.xp_spent,
            },
            status=status.HTTP_201_CREATED,
        )


# =============================================================================
# Resonance Pivot Spec C — Pose + Scene Entry Endorsement surfaces (Tasks 23, 24)
# =============================================================================

# Error messages — module constants keep tests stable and satisfy STRING_LITERAL.
_ERR_ENDORSEMENT_SETTLED = "Endorsement already settled."

# _resolve_actor_sheet and _resolve_endorser_sheet are imported at the top of this module
# from world.magic.services.auth — see import section above.


class PoseEndorsementViewSet(
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    GenericViewSet,
):
    """Create + delete-if-unsettled pose endorsements (Spec C Task 23).

    Listing is not supported here — use ResonanceGrantViewSet (Task 25) for
    audit queries.

    POST /api/magic/pose-endorsements/ — create an endorsement.
    DELETE /api/magic/pose-endorsements/<pk>/ — retract an unsettled endorsement.
    """

    queryset = PoseEndorsement.objects.select_related(
        "endorser_sheet",
        "endorsee_sheet",
        "interaction",
        "resonance",
    )
    serializer_class = PoseEndorsementSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer: PoseEndorsementSerializer) -> None:
        """Resolve the endorser sheet from the requesting account and save."""
        serializer.save(endorser_sheet=_resolve_endorser_sheet(self.request))

    def destroy(self, request: Request, *args: object, **kwargs: object) -> Response:
        """Delete an unsettled endorsement.

        Settled endorsements are hidden behind 404 — they are immutable once
        the weekly tick has run. Only the endorsing account can delete.
        """
        endorsement = self.get_object()
        if endorsement.settled_at is not None:
            raise Http404(_ERR_ENDORSEMENT_SETTLED)
        # Alt-guard: only the endorsing account can retract.
        if account_for_sheet(endorsement.endorser_sheet) != request.user:
            raise PermissionDenied
        endorsement.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SceneEntryEndorsementViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    GenericViewSet,
):
    """Create + retrieve — scene-entry endorsements are immutable (Spec C Task 24).

    DELETE is deferred until ResonanceGrantReversal ships. Grant fires
    immediately at creation time — no weekly settlement step. Retrieve is
    exposed so the detail URL is registered, which means DELETE returns 405
    (Method Not Allowed) rather than 404 (not found).

    POST /api/magic/scene-entry-endorsements/ — create an endorsement.
    GET  /api/magic/scene-entry-endorsements/<pk>/ — retrieve an endorsement.
    """

    queryset = SceneEntryEndorsement.objects.select_related(
        "endorser_sheet",
        "endorsee_sheet",
        "scene",
        "resonance",
    )
    serializer_class = SceneEntryEndorsementSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer: SceneEntryEndorsementSerializer) -> None:
        """Resolve the endorser sheet from the requesting account and save."""
        serializer.save(endorser_sheet=_resolve_endorser_sheet(self.request))


# =============================================================================
# Resonance Pivot Spec C — ResonanceGrant read-only ledger (Task 25)
# =============================================================================


class ResonanceGrantViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Read-only audit ledger of all grants. User-scoped; staff see all.

    GET  /api/magic/resonance-grants/       — list (user-scoped or staff-all)
    GET  /api/magic/resonance-grants/<pk>/  — retrieve one row

    Ordering: newest-first (descending granted_at). This is a timeline surface
    and ordering is justified per CLAUDE.md policy.

    Filter params: source, resonance (PK), granted_after, granted_before.
    """

    serializer_class = ResonanceGrantSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = ResonanceGrantFilterSet
    queryset = ResonanceGrant.objects.select_related(
        "character_sheet",
        "resonance",
    ).order_by("-granted_at")

    def get_queryset(self):  # type: ignore[override]
        qs = super().get_queryset()
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return qs
        return qs.filter(
            character_sheet__roster_entry__tenures__player_data__account=user,
            character_sheet__roster_entry__tenures__end_date__isnull=True,
        ).distinct()


# =============================================================================
# Resonance Pivot Spec B — Soul Tether API views (Phase 11)
# =============================================================================


class SoulTetherAcceptView(APIView):
    """Form a Soul Tether bond (Spec B §12).

    POST /api/magic/soul-tether/accept/

    Accepts ``{actor_sheet_id, partner_sheet_id, sinner_role, resonance_id, writeup}``.
    Calls ``accept_soul_tether``; returns the RelationshipCapstone PK on success.
    Service-level typed exceptions carry ``user_message`` and are mapped to HTTP 400
    inside the serializer.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        """Validate and dispatch accept_soul_tether; return capstone PK."""
        from world.magic.serializers import AcceptSoulTetherSerializer  # noqa: PLC0415

        serializer = AcceptSoulTetherSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        capstone = serializer.save()
        return Response({"capstone_id": capstone.pk}, status=status.HTTP_201_CREATED)


class SoulTetherDetailView(APIView):
    """View tether state (Spec B §18).

    GET /api/magic/soul-tether/{relationship_id}/

    Returns Hollow current/max, Thread levels, Sineater stats, and roles.
    Either party may retrieve; relationship_id may be either directional row.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, relationship_id: int) -> Response:
        """Fetch and serialise the tether state for the given relationship."""
        from world.magic.serializers import SoulTetherDetailSerializer  # noqa: PLC0415
        from world.relationships.models import CharacterRelationship  # noqa: PLC0415

        rel = get_object_or_404(CharacterRelationship, pk=relationship_id, is_soul_tether=True)
        serializer = SoulTetherDetailSerializer(rel, context={"request": request})
        return Response(serializer.data)


class SineatingRequestView(APIView):
    """Sinner-initiated Sineating request (Spec B §7).

    POST /api/magic/soul-tether/sineating/request/

    Accepts ``{actor_sheet_id, sineater_sheet_id, resonance_id, max_units, scene_id}``.
    Returns a ``SineatingOffer`` payload for the Sineater to accept or decline via
    the respond endpoint.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        """Validate and dispatch request_sineating; return offer payload."""
        from world.magic.serializers import (  # noqa: PLC0415
            SineatingOfferSerializer,
            SineatingRequestSerializer,
        )

        serializer = SineatingRequestSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        offer = serializer.save()
        return Response(
            SineatingOfferSerializer(offer).data,
            status=status.HTTP_200_OK,
        )


class SineatingRespondView(APIView):
    """Sineater accepts or declines a Sineating offer (Spec B §7).

    POST /api/magic/soul-tether/sineating/respond/

    Accepts ``{sinner_sheet_id, sineater_sheet_id, resonance_id, max_units,
    scene_id, units_accepted}``. Re-validates the offer server-side (Option B
    synchronous path) then calls ``resolve_sineating``. Returns the result.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        """Re-validate offer + dispatch resolve_sineating; return result payload."""
        from world.magic.serializers import (  # noqa: PLC0415
            SineatingRespondSerializer,
            SineatingResultSerializer,
        )

        serializer = SineatingRespondSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        return Response(
            SineatingResultSerializer(result).data,
            status=status.HTTP_200_OK,
        )


class SoulTetherRescueView(APIView):
    """Sineater performs stage-3+ rescue ritual (Spec B §9).

    POST /api/magic/soul-tether/rescue/

    Accepts ``{actor_sheet_id, sinner_sheet_id, resonance_id, scene_id}``.
    Calls ``perform_soul_tether_rescue``; returns the RescueOutcome payload.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        """Validate and dispatch perform_soul_tether_rescue; return outcome payload."""
        from world.magic.serializers import (  # noqa: PLC0415
            RescueOutcomeSerializer,
            SoulTetherRescueSerializer,
        )

        serializer = SoulTetherRescueSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        outcome = serializer.save()
        return Response(
            RescueOutcomeSerializer(outcome).data,
            status=status.HTTP_200_OK,
        )


class SoulTetherDissolveView(APIView):
    """Dissolve a Soul Tether bond (Spec B §13).

    POST /api/magic/soul-tether/dissolve/

    Accepts ``{actor_sheet_id, relationship_id}``. Either party may dissolve.
    Calls ``dissolve_soul_tether``; returns HTTP 204 on success.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        """Validate and dispatch dissolve_soul_tether; return 204 on success."""
        from world.magic.serializers import DissolveSerializer  # noqa: PLC0415

        serializer = DissolveSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SineatingPendingOfferViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only Sineater-facing inbox of pending Sineating offers (Task 1.6).

    GET /api/magic/soul-tether/sineating/pending/
    GET /api/magic/soul-tether/sineating/pending/{id}/

    Scoped to the authenticated user as the Sineater — returns only offers where
    the caller's character sheets appear as the Sineater.
    """

    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_serializer_class(self) -> type:
        from world.magic.serializers import SineatingPendingOfferSerializer  # noqa: PLC0415

        return SineatingPendingOfferSerializer

    def get_queryset(self):
        from world.magic.models.soul_tether import SineatingPendingOffer  # noqa: PLC0415

        user = self.request.user
        # Resolve the authenticated user to their character sheets via the
        # Roster tenure chain (CharacterSheet → RosterEntry → RosterTenure
        # → PlayerData → AccountDB). Filter to active tenures only
        # (end_date__isnull=True) to avoid surfacing stale character
        # associations, and use distinct() to prevent duplicates when a sheet
        # has multiple past tenures for the same account.
        return (
            SineatingPendingOffer.objects.filter(
                sineater_sheet__roster_entry__tenures__player_data__account=user,
                sineater_sheet__roster_entry__tenures__end_date__isnull=True,
            )
            .select_related("sinner_sheet", "scene", "resonance")
            .order_by("-created_at")
            .distinct()
        )


class PendingStageAdvanceOfferViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only Sineater-facing inbox of pending stage-advance bonus offers (Task 1.7).

    GET /api/magic/soul-tether/stage-advance/pending/
    GET /api/magic/soul-tether/stage-advance/pending/{id}/

    Scoped to the authenticated user as the Sineater — returns only offers where
    the caller's character sheets appear as the Sineater. The UI should also
    filter client-side by ``expires_at`` to hide already-expired rows (the server
    does not proactively prune; rows are deleted on the next respond attempt).
    """

    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_serializer_class(self) -> type:
        from world.magic.serializers import PendingStageAdvanceOfferSerializer  # noqa: PLC0415

        return PendingStageAdvanceOfferSerializer

    def get_queryset(self):
        from world.magic.models.soul_tether import PendingStageAdvanceOffer  # noqa: PLC0415

        user = self.request.user
        return (
            PendingStageAdvanceOffer.objects.filter(
                sineater_sheet__roster_entry__tenures__player_data__account=user,
                sineater_sheet__roster_entry__tenures__end_date__isnull=True,
            )
            .select_related("sinner_sheet", "scene", "resonance")
            .order_by("-created_at")
            .distinct()
        )


class StageAdvanceRespondView(APIView):
    """Sineater accepts or declines a stage-advance bonus offer (Spec B §8.1).

    POST /api/magic/soul-tether/stage-advance/respond/

    Looks up the persisted ``PendingStageAdvanceOffer`` row, validates TTL and
    co-location, then delegates to ``resolve_stage_advance_prompt_from_db``.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        """Validate offer + dispatch resolve; return result payload."""
        from world.magic.serializers import (  # noqa: PLC0415
            StageAdvanceBonusResultSerializer,
            StageAdvanceRespondSerializer,
        )

        serializer = StageAdvanceRespondSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        result = serializer.save()

        out = StageAdvanceBonusResultSerializer(result)
        return Response(out.data, status=status.HTTP_200_OK)


# =============================================================================
# Thread Hub Summary (GET /api/magic/thread-hub-summary/)
# =============================================================================


class ThreadHubSummaryView(APIView):
    """Aggregate dashboard payload for the Thread Hub page.

    Returns resonance balances, prospect ID lists (ready/near-xp-lock/blocked),
    and per-TargetKind weaving eligibility flags in one round-trip.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: ThreadHubSummarySerializer},
    )
    def get(self, request: Request) -> Response:
        """Return the Thread Hub summary for the acting character."""
        from world.magic.constants import TargetKind  # noqa: PLC0415
        from world.magic.models.weaving import CharacterThreadWeavingUnlock  # noqa: PLC0415
        from world.magic.services.threads import (  # noqa: PLC0415
            imbue_ready_threads,
            near_xp_lock_threads,
            threads_blocked_by_cap,
            weaving_eligibility_for,
        )
        from world.traits.models import CharacterTraitValue  # noqa: PLC0415

        sheet = _resolve_actor_sheet(request, body_key="character_sheet_id", from_query=True)
        balances = [
            {
                "resonance_id": cr.resonance_id,
                "balance": cr.balance,
                "lifetime_earned": cr.lifetime_earned,
                "flavor_text": cr.flavor_text,
            }
            for cr in CharacterResonance.objects.filter(character_sheet=sheet)
        ]
        ready = [t.pk for t in imbue_ready_threads(sheet)]
        near = [
            {
                "thread_id": p.thread.pk,
                "boundary_level": p.boundary_level,
                "xp_cost": p.xp_cost,
                "dev_points_to_boundary": p.dev_points_to_boundary,
            }
            for p in near_xp_lock_threads(sheet)
        ]
        blocked = [t.pk for t in threads_blocked_by_cap(sheet)]
        eligibility = weaving_eligibility_for(sheet)

        # Picker data for the Weave Thread Wizard anchor steps.
        # Reads from character handler caches — zero extra queries after first load.
        unlocks = list(
            CharacterThreadWeavingUnlock.objects.filter(character=sheet).select_related(
                "unlock",
                "unlock__unlock_trait",
                "unlock__unlock_gift",
            )
        )
        character = sheet.character
        weavable_traits: list[dict] = []
        weavable_techniques: list[dict] = []
        room_property_ids: list[int] = []
        weavable_relationship_track_ids: list[int] = []

        for cu in unlocks:
            unlock = cu.unlock
            kind = unlock.target_kind

            if kind == TargetKind.TRAIT and unlock.unlock_trait_id:
                trait = unlock.unlock_trait
                tv = character.traits.get_trait_object(trait.name)
                if isinstance(tv, CharacterTraitValue) and tv.value > 0:
                    weavable_traits.append(
                        {
                            "trait_id": trait.pk,
                            "name": trait.name,
                            "trait_type": trait.trait_type,
                            "display_value": tv.display_value,
                        }
                    )
            elif kind == TargetKind.TECHNIQUE and unlock.unlock_gift_id:
                gift = unlock.unlock_gift
                weavable_techniques.extend(
                    {
                        "technique_id": technique.pk,
                        "name": technique.name,
                        "gift_id": gift.pk,
                        "gift_name": gift.name,
                    }
                    for technique in character.techniques.all()
                    if technique.gift_id == gift.pk
                )
            elif kind == TargetKind.ROOM and unlock.unlock_room_property_id:
                room_property_ids.append(unlock.unlock_room_property_id)
            elif kind == TargetKind.RELATIONSHIP_TRACK and unlock.unlock_track_id:
                weavable_relationship_track_ids.append(unlock.unlock_track_id)

        payload = {
            "balances": balances,
            "ready_thread_ids": ready,
            "near_xp_lock_thread_ids": near,
            "blocked_thread_ids": blocked,
            "weaving_eligibility": eligibility,
            "weavable_traits": weavable_traits,
            "weavable_techniques": weavable_techniques,
            "room_property_ids": room_property_ids,
            "weavable_relationship_track_ids": weavable_relationship_track_ids,
        }
        return Response(ThreadHubSummarySerializer(payload).data)


# =============================================================================
# Rooms-by-property (GET /api/magic/rooms-by-property/)
# =============================================================================


class RitualSessionViewSet(viewsets.ModelViewSet):
    """Multi-participant ritual session endpoints (Covenants Slice B §4.12).

    Scoping (non-staff): sessions where the user is initiator OR invited participant.
    Staff: all sessions.

    Actions:
    - list / retrieve: read
    - create: draft (initiator-only, non-SINGLE_ACTOR rituals)
    - destroy: cancel (initiator-only)
    - accept / decline: participant-only
    - fire: initiator-only, threshold-gated
    """

    pagination_class = None
    filter_backends = [DjangoFilterBackend]
    filterset_class = RitualSessionFilterSet
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Scope to sessions where user is initiator or invited participant."""
        from django.db.models import Q  # noqa: PLC0415

        from world.magic.models.sessions import (  # noqa: PLC0415
            RitualSession,
            RitualSessionParticipant,
            RitualSessionReference,
        )

        qs = RitualSession.objects.select_related("ritual", "initiator").prefetch_related(
            Prefetch(
                "participants",
                queryset=RitualSessionParticipant.objects.select_related("character_sheet"),
                to_attr="participants_cached",
            ),
            Prefetch(
                "references",
                queryset=RitualSessionReference.objects.all(),
                to_attr="references_cached",
            ),
        )
        user = self.request.user
        if user.is_staff:
            return qs.order_by("-created_at")
        my_sheet_ids = list(RosterEntry.objects.for_account(cast(AccountDB, user)).character_ids())
        return (
            qs.filter(
                Q(initiator_id__in=my_sheet_ids)
                | Q(participants__character_sheet_id__in=my_sheet_ids)
            )
            .distinct()
            .order_by("-created_at")
        )

    def get_serializer_class(self):
        from world.magic.serializers import (  # noqa: PLC0415
            RitualSessionAcceptSerializer,
            RitualSessionDetailSerializer,
            RitualSessionDraftSerializer,
            RitualSessionListSerializer,
        )

        if self.action == "create":
            return RitualSessionDraftSerializer
        if self.action == "retrieve":
            return RitualSessionDetailSerializer
        if self.action in ("accept", "decline"):
            return RitualSessionAcceptSerializer
        return RitualSessionListSerializer

    def get_permissions(self):
        from world.magic.permissions import (  # noqa: PLC0415
            IsInvitedParticipant,
            IsRitualSessionInitiator,
            IsRitualSessionParticipantOrInitiator,
        )

        if self.action == "destroy":
            return [IsAuthenticated(), IsRitualSessionInitiator()]
        if self.action == "fire":
            return [IsAuthenticated(), IsRitualSessionInitiator()]
        if self.action in ("accept", "decline"):
            return [IsAuthenticated(), IsInvitedParticipant()]
        if self.action == "retrieve":
            return [IsAuthenticated(), IsRitualSessionParticipantOrInitiator()]
        return super().get_permissions()

    def perform_create(self, serializer) -> None:
        """Call draft_session with the serializer's validated_data."""
        from world.magic.services.sessions import draft_session  # noqa: PLC0415

        session = draft_session(**serializer.validated_data)
        serializer.instance = session

    def perform_destroy(self, instance) -> None:
        """Cancel = delete via the typed service (which has its own select_for_update)."""
        from world.magic.services.sessions import cancel_session  # noqa: PLC0415

        cancel_session(session=instance)

    @extend_schema(
        request=RitualSessionDraftSerializer,
        responses={201: RitualSessionDetailSerializer},
    )
    def create(self, request: Request, *args, **kwargs) -> Response:
        """POST /api/rituals/sessions/ — draft a new session.

        Request body: RitualSessionDraftSerializer.
        Response: RitualSessionDetailSerializer (201) — includes the new
        session's id so the frontend can navigate to its detail page.
        """
        from world.magic.exceptions import (  # noqa: PLC0415
            ParticipantCountError,
            RitualSessionError,
        )

        serializer = RitualSessionDraftSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        try:
            self.perform_create(serializer)
        except (RitualSessionError, ParticipantCountError) as exc:
            return Response({"detail": exc.user_message}, status=status.HTTP_400_BAD_REQUEST)
        out = RitualSessionDetailSerializer(serializer.instance, context={"request": request})
        return Response(out.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def accept(self, request: Request, pk: int | None = None) -> Response:
        """Accept invitation, supplying participant_kwargs + references."""
        from world.magic.exceptions import RitualSessionError  # noqa: PLC0415
        from world.magic.models.sessions import RitualSessionParticipant  # noqa: PLC0415
        from world.magic.serializers import (  # noqa: PLC0415
            RitualSessionAcceptSerializer,
            RitualSessionDetailSerializer,
        )
        from world.magic.services.sessions import accept_session  # noqa: PLC0415

        session = self.get_object()
        user = request.user
        my_sheet_ids = set(RosterEntry.objects.for_account(cast(AccountDB, user)).character_ids())
        participant = RitualSessionParticipant.objects.filter(
            session=session,
            character_sheet_id__in=my_sheet_ids,
        ).first()
        if participant is None:
            return Response(
                {"detail": "You are not an invited participant of this session."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = RitualSessionAcceptSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            accept_session(
                participant=participant,
                participant_kwargs=data.get("participant_kwargs", {}),
                references=data.get("references", []),
            )
        except RitualSessionError as exc:
            return Response({"detail": exc.user_message}, status=status.HTTP_400_BAD_REQUEST)
        session.refresh_from_db()
        out = RitualSessionDetailSerializer(session, context={"request": request})
        return Response(out.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def decline(self, request: Request, pk: int | None = None) -> Response:
        """Decline invitation. Returns 204 if session was deleted, 200 otherwise."""
        from world.magic.exceptions import RitualSessionError  # noqa: PLC0415
        from world.magic.models.sessions import RitualSessionParticipant  # noqa: PLC0415
        from world.magic.serializers import RitualSessionDetailSerializer  # noqa: PLC0415
        from world.magic.services.sessions import decline_session  # noqa: PLC0415

        session = self.get_object()
        user = request.user
        my_sheet_ids = set(RosterEntry.objects.for_account(cast(AccountDB, user)).character_ids())
        participant = RitualSessionParticipant.objects.filter(
            session=session,
            character_sheet_id__in=my_sheet_ids,
        ).first()
        if participant is None:
            return Response(
                {"detail": "You are not an invited participant of this session."},
                status=status.HTTP_403_FORBIDDEN,
            )
        session_pk = session.pk
        try:
            decline_session(participant=participant)
        except RitualSessionError as exc:
            return Response({"detail": exc.user_message}, status=status.HTTP_400_BAD_REQUEST)
        # If session was deleted by the decline, return 204.
        from world.magic.models.sessions import RitualSession  # noqa: PLC0415

        if not RitualSession.objects.filter(pk=session_pk).exists():
            return Response(status=status.HTTP_204_NO_CONTENT)
        session.refresh_from_db()
        out = RitualSessionDetailSerializer(session, context={"request": request})
        return Response(out.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def fire(self, request: Request, pk: int | None = None) -> Response:
        """Initiator-only fire. Returns {result_kind, result_id} envelope."""
        from world.covenants.exceptions import CovenantError  # noqa: PLC0415
        from world.magic.constants import ParticipationRule  # noqa: PLC0415
        from world.magic.exceptions import RitualSessionError  # noqa: PLC0415
        from world.magic.services.sessions import fire_session  # noqa: PLC0415

        session = self.get_object()
        rule = session.ritual.participation_rule
        try:
            result = fire_session(session=session)
        except RitualSessionError as exc:
            return Response({"detail": exc.user_message}, status=status.HTTP_400_BAD_REQUEST)
        except CovenantError as exc:
            return Response({"detail": exc.user_message}, status=status.HTTP_400_BAD_REQUEST)
        if rule == ParticipationRule.FORMATION:
            result_kind = "covenant"
        elif rule == ParticipationRule.INDUCTION:
            result_kind = "membership"
        elif rule == ParticipationRule.BILATERAL:
            # Soul Tether returns a RelationshipCapstone.
            result_kind = "capstone"
        else:
            result_kind = "unknown"
        result_id = getattr(result, "pk", None)  # noqa: GETATTR_LITERAL
        return Response(
            {"result_kind": result_kind, "result_id": result_id},
            status=status.HTTP_200_OK,
        )


class RoomsByPropertyView(APIView):
    """List rooms (ObjectDB) bearing any of the requested Property ids.

    Used by the Weave Thread wizard to populate the ROOM-anchor picker.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: RoomBriefSerializer(many=True)},
    )
    def get(self, request: Request) -> Response:
        """Return rooms that have at least one matching ObjectProperty."""
        from world.magic.serializers import RoomsByPropertyQuerySerializer  # noqa: PLC0415

        serializer = RoomsByPropertyQuerySerializer(
            data={"property_ids": request.query_params.getlist("property_id")},
        )
        serializer.is_valid(raise_exception=True)
        ids = serializer.validated_data["property_ids"]
        rooms = (
            ObjectDB.objects.filter(object_properties__property__in=ids)
            .annotate(name=F("db_key"))
            .distinct()
            .values("id", "name")
        )
        return Response(list(rooms))


class ApplicablePullsView(APIView):
    """POST /api/magic/applicable-pulls/ → per-thread applicability rows.

    Returns one row per active (non-retired) thread owned by the requested
    character sheet. Each row carries ``{thread_id, applicable, inapplicable_reason}``.
    ``inapplicable_reason`` is null when ``applicable`` is true.

    Permission: requester must own the character sheet (staff bypass).
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=ApplicablePullsRequestSerializer,
        responses={200: ThreadApplicabilitySerializer(many=True)},
    )
    def post(self, request: Request) -> Response:
        """Compute and return per-thread applicability for the given action context."""
        serializer = ApplicablePullsRequestSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # character_sheet_id was resolved + ownership-checked by the serializer.
        sheet: CharacterSheet = data["character_sheet_id"]

        technique = None
        technique_id = data.get("technique_id")
        if technique_id:
            technique = Technique.objects.filter(pk=technique_id).first()

        context = PullActionContext(
            technique=technique,
            effect_type_id=data.get("effect_type_id"),
            target_object_id=data.get("target_object_id"),
            target_persona_id=data.get("target_persona_id"),
            scene_id=data.get("scene_id"),
        )
        rows = compute_thread_applicability(sheet, context)
        return Response(ThreadApplicabilitySerializer(rows, many=True).data)
