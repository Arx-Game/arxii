"""
API views for the magic system.

This module provides ViewSets for:
- Lookup tables (read-only): ThreadType, TechniqueStyle, EffectType, Restriction, Facet
- CG CRUD: Gift, Technique
- Character magic data: Aura, Gifts, Anima, Rituals
- Threads (relationships): Thread, ThreadJournal, ThreadResonance

Note: Affinity and Resonance are now ModifierType entries in the mechanics app.
Use the mechanics API endpoints for those lookups.
"""

from django.db.models import Count, Prefetch, Q
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from world.magic.models import (
    CharacterAnima,
    CharacterAnimaRitual,
    CharacterAura,
    CharacterFacet,
    CharacterGift,
    CharacterResonance,
    EffectType,
    Facet,
    Gift,
    Restriction,
    Technique,
    TechniqueStyle,
    Thread,
    ThreadJournal,
    ThreadResonance,
    ThreadType,
)
from world.magic.serializers import (
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
    RestrictionSerializer,
    TechniqueSerializer,
    TechniqueStyleSerializer,
    ThreadJournalSerializer,
    ThreadListSerializer,
    ThreadResonanceSerializer,
    ThreadSerializer,
    ThreadTypeSerializer,
)
from world.stories.pagination import StandardResultsSetPagination

# =============================================================================
# Lookup Table ViewSets (Read-Only)
# =============================================================================

# Note: Affinity and Resonance ViewSets have been removed.
# These are now served from the mechanics app as ModifierType entries
# filtered by category (affinity or resonance).


class ThreadTypeViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for ThreadType lookup records.

    Provides read-only access to relationship types that emerge
    based on thread axis thresholds.
    """

    queryset = ThreadType.objects.select_related(
        "grants_resonance", "grants_resonance__category"
    ).order_by("name")
    serializer_class = ThreadTypeSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None  # ~17 thread types


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
        # Only top-level facets, children are nested by serializer
        top_level = Facet.objects.filter(parent__isnull=True).prefetch_related(
            "children__children__children"
        )
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
        queryset = CharacterFacet.objects.select_related("facet", "facet__parent", "resonance")
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
        Gift.objects.select_related("affinity", "affinity__category")
        .prefetch_related(
            Prefetch("resonances", to_attr="cached_resonances"),
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
        .prefetch_related("restrictions")
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
        if user.is_staff:
            return CharacterResonance.objects.select_related(
                "resonance", "resonance__category"
            ).all()
        return CharacterResonance.objects.select_related("resonance", "resonance__category").filter(
            character__db_account=user
        )


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
        queryset = CharacterGift.objects.select_related(
            "gift__affinity",
            "gift__affinity__category",
        ).prefetch_related(
            "gift__resonances",
            "gift__resonances__category",
            "gift__techniques__style",
            "gift__techniques__effect_type",
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
            "resonance__category",
        )
        if user.is_staff:
            return queryset
        return queryset.filter(character__character__db_account=user)


# =============================================================================
# Thread (Relationship) ViewSets
# =============================================================================


class ThreadViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Thread records.

    Manages magical connections between characters. Users can only
    access threads involving characters they own.
    """

    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter to threads involving characters owned by the current user."""
        user = self.request.user
        queryset = Thread.objects.select_related(
            "initiator",
            "receiver",
        ).prefetch_related(
            "resonances__resonance",
        )
        if user.is_staff:
            return queryset
        # TODO: db_account filtering may not work correctly - character ownership
        # should go through roster once that integration is complete.
        # See: https://github.com/Arx-Game/arxii/pull/XXX for discussion
        return queryset.filter(Q(initiator__db_account=user) | Q(receiver__db_account=user))

    def get_serializer_class(self):
        """Use lightweight serializer for list, full serializer for detail."""
        if self.action == "list":
            return ThreadListSerializer
        return ThreadSerializer


class ThreadJournalViewSet(viewsets.ModelViewSet):
    """
    ViewSet for ThreadJournal records.

    Manages IC-visible journal entries on threads.
    """

    serializer_class = ThreadJournalSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter to journals on threads the user can access."""
        user = self.request.user
        queryset = ThreadJournal.objects.select_related(
            "thread__initiator",
            "thread__receiver",
            "author",
        )
        if user.is_staff:
            return queryset
        # TODO: db_account filtering may not work correctly - see ThreadViewSet
        return queryset.filter(
            Q(thread__initiator__db_account=user) | Q(thread__receiver__db_account=user)
        )


class ThreadResonanceViewSet(viewsets.ModelViewSet):
    """
    ViewSet for ThreadResonance records.

    Manages resonances attached to threads.
    """

    serializer_class = ThreadResonanceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter to resonances on threads the user can access."""
        user = self.request.user
        queryset = ThreadResonance.objects.select_related(
            "thread__initiator",
            "thread__receiver",
            "resonance",
            "resonance__category",
        )
        if user.is_staff:
            return queryset
        # TODO: db_account filtering may not work correctly - see ThreadViewSet
        return queryset.filter(
            Q(thread__initiator__db_account=user) | Q(thread__receiver__db_account=user)
        )
