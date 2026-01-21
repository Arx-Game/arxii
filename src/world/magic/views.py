"""
API views for the magic system.

This module provides ViewSets for:
- Lookup tables (read-only): Affinity, Resonance, IntensityTier, etc.
- Character magic data: Aura, Gifts, Powers, Anima, Rituals
- Threads (relationships): Thread, ThreadJournal, ThreadResonance
"""

from django.db.models import Q
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from world.magic.models import (
    Affinity,
    AnimaRitualType,
    CharacterAnima,
    CharacterAnimaRitual,
    CharacterAura,
    CharacterGift,
    CharacterPower,
    CharacterResonance,
    Gift,
    IntensityTier,
    Power,
    Resonance,
    Thread,
    ThreadJournal,
    ThreadResonance,
    ThreadType,
)
from world.magic.serializers import (
    AffinitySerializer,
    AnimaRitualTypeSerializer,
    CharacterAnimaRitualSerializer,
    CharacterAnimaSerializer,
    CharacterAuraSerializer,
    CharacterGiftSerializer,
    CharacterPowerSerializer,
    CharacterResonanceSerializer,
    GiftListSerializer,
    GiftSerializer,
    IntensityTierSerializer,
    PowerSerializer,
    ResonanceSerializer,
    ThreadJournalSerializer,
    ThreadListSerializer,
    ThreadResonanceSerializer,
    ThreadSerializer,
    ThreadTypeSerializer,
)

# =============================================================================
# Lookup Table ViewSets (Read-Only)
# =============================================================================


class AffinityViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for Affinity lookup records.

    Provides read-only access to the three magical affinities:
    Celestial, Primal, and Abyssal.
    """

    queryset = Affinity.objects.all()
    serializer_class = AffinitySerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None  # Only 3 affinities


class ResonanceViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for Resonance lookup records.

    Provides read-only access to all available resonances (style tags)
    that can be attached to characters, items, rooms, etc.
    """

    queryset = Resonance.objects.select_related("default_affinity").order_by("name")
    serializer_class = ResonanceSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None  # ~40 resonances, small enough to load all


class IntensityTierViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for IntensityTier lookup records.

    Provides read-only access to intensity tier thresholds
    that determine power effect levels.
    """

    queryset = IntensityTier.objects.all().order_by("threshold")
    serializer_class = IntensityTierSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None  # Only 6 tiers


class AnimaRitualTypeViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for AnimaRitualType lookup records.

    Provides read-only access to predefined anima ritual types
    that characters can personalize for recovery.
    """

    queryset = AnimaRitualType.objects.all().order_by("category", "name")
    serializer_class = AnimaRitualTypeSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None  # ~20 ritual types


class ThreadTypeViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for ThreadType lookup records.

    Provides read-only access to relationship types that emerge
    based on thread axis thresholds.
    """

    queryset = ThreadType.objects.select_related("grants_resonance").order_by("name")
    serializer_class = ThreadTypeSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None  # ~17 thread types


class GiftViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for Gift records.

    Provides read-only access to magical gift definitions.
    List view uses lightweight serializer; detail view includes powers.
    """

    queryset = Gift.objects.select_related("affinity").prefetch_related(
        "resonances",
        "powers__affinity",
        "powers__resonances",
    )
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        """Use lightweight serializer for list, full serializer for detail."""
        if self.action == "list":
            return GiftListSerializer
        return GiftSerializer


class PowerViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for Power records.

    Provides read-only access to individual power definitions.
    """

    queryset = Power.objects.select_related(
        "gift",
        "affinity",
    ).prefetch_related("resonances")
    serializer_class = PowerSerializer
    permission_classes = [IsAuthenticated]


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
            return CharacterResonance.objects.select_related("resonance").all()
        return CharacterResonance.objects.select_related("resonance").filter(
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
        ).prefetch_related(
            "gift__resonances",
            "gift__powers__affinity",
            "gift__powers__resonances",
        )
        if user.is_staff:
            return queryset
        return queryset.filter(character__db_account=user)


class CharacterPowerViewSet(viewsets.ModelViewSet):
    """
    ViewSet for CharacterPower records.

    Manages powers unlocked by characters.
    """

    serializer_class = CharacterPowerSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter to characters owned by the current user."""
        user = self.request.user
        queryset = CharacterPower.objects.select_related(
            "power__gift",
            "power__affinity",
        ).prefetch_related("power__resonances")
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
        queryset = CharacterAnimaRitual.objects.select_related("ritual_type")
        if user.is_staff:
            return queryset
        return queryset.filter(character__db_account=user)


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
        )
        if user.is_staff:
            return queryset
        # TODO: db_account filtering may not work correctly - see ThreadViewSet
        return queryset.filter(
            Q(thread__initiator__db_account=user) | Q(thread__receiver__db_account=user)
        )
