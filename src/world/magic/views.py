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

from django.db.models import Count, Prefetch
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from evennia.accounts.models import AccountDB
from rest_framework import status, viewsets
from rest_framework.decorators import action
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
    ThreadFilter,
    ThreadWeavingTeachingOfferFilter,
)
from world.magic.models import (
    Cantrip,
    CharacterAnima,
    CharacterAnimaRitual,
    CharacterAura,
    CharacterFacet,
    CharacterGift,
    CharacterResonance,
    EffectType,
    Facet,
    Gift,
    MagicalAlterationTemplate,
    PendingAlteration,
    Resonance,
    Restriction,
    Technique,
    TechniqueStyle,
    Thread,
    ThreadWeavingTeachingOffer,
)
from world.magic.permissions import IsThreadOwner
from world.magic.serializers import (
    AlterationResolutionSerializer,
    CantripSerializer,
    CharacterAnimaRitualSerializer,
    CharacterAnimaSerializer,
    CharacterAuraSerializer,
    CharacterFacetSerializer,
    CharacterGiftSerializer,
    CharacterResonanceSerializer,
    EffectTypeSerializer,
    FacetSerializer,
    FacetTreeSerializer,
    GiftCreateSerializer,
    GiftListSerializer,
    GiftSerializer,
    LibraryEntrySerializer,
    PendingAlterationSerializer,
    RestrictionSerializer,
    RitualPerformRequestSerializer,
    TechniqueSerializer,
    TechniqueStyleSerializer,
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
from world.roster.models import RosterEntry
from world.stories.pagination import StandardResultsSetPagination

# Error messages — module constants keep tests stable and satisfy STRING_LITERAL.
_ERR_NO_CHARACTER = "No active character found for this account."
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


class CharacterFacetViewSet(viewsets.ModelViewSet):
    """
    ViewSet for CharacterFacet records.

    Manages facet assignments for characters.
    """

    serializer_class = CharacterFacetSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter to characters owned by the current user."""
        user = self.request.user
        queryset = CharacterFacet.objects.select_related(
            "facet",
            "facet__parent",
            "resonance",
            "resonance__affinity",
            "resonance__modifier_target__codex_entry",
        )
        if user.is_staff:
            return queryset
        return queryset.filter(character__character__db_account=user)


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

    Provides access to character aura data. Users can only access
    auras for characters they own (or all if staff).
    """

    serializer_class = CharacterAuraSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter to characters owned by the current user."""
        user = self.request.user
        if user.is_staff:
            return CharacterAura.objects.all()
        # Filter to characters owned by this account
        return CharacterAura.objects.filter(character__db_account=user)


class CharacterResonanceViewSet(viewsets.ModelViewSet):
    """
    ViewSet for CharacterResonance records.

    Manages personal resonances attached to characters.
    """

    serializer_class = CharacterResonanceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter to characters owned by the current user."""
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
        return queryset.filter(character_sheet__character__db_account=user)


class CharacterGiftViewSet(viewsets.ModelViewSet):
    """
    ViewSet for CharacterGift records.

    Manages gifts possessed by characters.
    """

    serializer_class = CharacterGiftSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter to characters owned by the current user."""
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
        return queryset.filter(character__db_account=user)


class CharacterAnimaViewSet(viewsets.ModelViewSet):
    """
    ViewSet for CharacterAnima records.

    Manages character anima (magical energy) tracking.
    """

    serializer_class = CharacterAnimaSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter to characters owned by the current user."""
        user = self.request.user
        if user.is_staff:
            return CharacterAnima.objects.all()
        return CharacterAnima.objects.filter(character__db_account=user)


class CharacterAnimaRitualViewSet(viewsets.ModelViewSet):
    """
    ViewSet for CharacterAnimaRitual records.

    Manages personalized anima recovery rituals for characters.
    """

    serializer_class = CharacterAnimaRitualSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter to characters owned by the current user."""
        user = self.request.user
        queryset = CharacterAnimaRitual.objects.select_related(
            "stat",
            "skill",
            "specialization",
            "resonance",
            "resonance__affinity",
            "resonance__modifier_target__codex_entry",
        )
        if user.is_staff:
            return queryset
        return queryset.filter(character__character__db_account=user)


# =============================================================================
# Alteration ViewSets
# =============================================================================


class PendingAlterationViewSet(
    ListModelMixin,
    RetrieveModelMixin,
    GenericViewSet,
):
    """ViewSet for pending magical alterations.

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


def _account_character_sheet(user: AccountDB) -> CharacterSheet | None:
    """Return the requesting account's active CharacterSheet, or None.

    Mirrors the pattern used in combat.views.CombatEncounterViewSet.join — we
    resolve via the account's active roster tenure(s). Returns the first sheet
    found; callers that need an explicit persona selection should provide one.
    """
    character_ids = RosterEntry.objects.for_account(user).character_ids()
    return CharacterSheet.objects.filter(character_id__in=character_ids).first()


class ThreadViewSet(viewsets.ModelViewSet):
    """ViewSet for Thread records (Spec A §4.5).

    list / retrieve: returns threads the requesting account owns (staff can
    see all), excluding soft-retired rows.
    create: delegates to the serializer, which calls ``weave_thread``.
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
        qs = Thread.objects.filter(retired_at__isnull=True).select_related(
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
        if user.is_staff:
            return qs
        character_ids = RosterEntry.objects.for_account(
            cast(AccountDB, user),
        ).character_ids()
        return qs.filter(owner_id__in=character_ids)

    def get_serializer_context(self) -> dict:
        """Inject the caller's CharacterSheet so ThreadSerializer.create can use it."""
        context = super().get_serializer_context()
        user = self.request.user
        if user.is_authenticated and not user.is_anonymous:
            sheet = _account_character_sheet(cast(AccountDB, user))
            context["character_sheet"] = sheet
        return context

    def create(self, request: Request, *args, **kwargs) -> Response:
        """Require a resolvable character sheet before delegating to the serializer."""
        sheet = self.get_serializer_context().get("character_sheet")
        if sheet is None:
            return Response(
                {"detail": _ERR_NO_CHARACTER},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().create(request, *args, **kwargs)

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


class ThreadPullPreviewView(APIView):
    """Read-only preview of a resonance pull (Spec A §5.6).

    POST /api/magic/thread-pull-preview/

    Request body: ``{resonance_id, tier, thread_ids[], action_context?}``.
    Response: ``{resonance_cost, anima_cost, affordable, resolved_effects[],
    capped_intensity}``. Never mutates state.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        """Run the preview and return its wire representation."""
        sheet = _account_character_sheet(cast(AccountDB, request.user))
        if sheet is None:
            return Response(
                {"detail": _ERR_NO_CHARACTER},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = ThreadPullPreviewRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

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
        sheet = _account_character_sheet(cast(AccountDB, request.user))
        if sheet is None:
            return Response(
                {"detail": _ERR_NO_CHARACTER},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = RitualPerformRequestSerializer(
            data=request.data,
            context={"actor": sheet},
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

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
        "unlock",
        "unlock__unlock_trait",
        "unlock__unlock_gift",
        "unlock__unlock_room_property",
        "unlock__unlock_track",
    )
    serializer_class = ThreadWeavingTeachingOfferSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = ThreadWeavingTeachingOfferFilter
