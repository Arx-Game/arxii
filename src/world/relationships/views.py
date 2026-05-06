"""API views for the relationships system."""

from django.db.models import Prefetch
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ReadOnlyModelViewSet

from world.mechanics.models import ModifierTarget
from world.relationships.filters import RelationshipCapstoneFilter
from world.relationships.models import (
    CharacterRelationship,
    HybridRelationshipType,
    HybridRequirement,
    RelationshipCapstone,
    RelationshipCondition,
    RelationshipTier,
    RelationshipTrack,
    RelationshipTrackProgress,
    RelationshipUpdate,
)
from world.relationships.serializers import (
    CharacterRelationshipListSerializer,
    CharacterRelationshipSerializer,
    HybridRelationshipTypeSerializer,
    RelationshipCapstoneSerializer,
    RelationshipConditionSerializer,
    RelationshipTrackSerializer,
)


class RelationshipConditionViewSet(ReadOnlyModelViewSet):
    """List and retrieve relationship conditions."""

    queryset = RelationshipCondition.objects.prefetch_related(
        Prefetch(
            "gates_modifiers",
            queryset=ModifierTarget.objects.all(),
            to_attr="cached_gates_modifiers",
        ),
    )
    serializer_class = RelationshipConditionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None


class RelationshipTrackViewSet(ReadOnlyModelViewSet):
    """List and retrieve relationship tracks with nested tiers."""

    queryset = RelationshipTrack.objects.prefetch_related(
        Prefetch(
            "tiers",
            queryset=RelationshipTier.objects.all(),
            to_attr="cached_tiers",
        ),
    )
    serializer_class = RelationshipTrackSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None


class HybridRelationshipTypeViewSet(ReadOnlyModelViewSet):
    """List and retrieve hybrid relationship types with nested requirements."""

    queryset = HybridRelationshipType.objects.prefetch_related(
        Prefetch(
            "requirements",
            queryset=HybridRequirement.objects.select_related("track"),
            to_attr="cached_requirements",
        ),
    )
    serializer_class = HybridRelationshipTypeSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None


class CharacterRelationshipViewSet(ReadOnlyModelViewSet):
    """List and retrieve character relationships."""

    permission_classes = [IsAuthenticated]
    pagination_class = PageNumberPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["source", "target", "is_active", "is_pending"]

    def get_queryset(self):  # type: ignore[override]
        """Return relationships with related data prefetched."""
        return CharacterRelationship.objects.select_related(
            "source",
            "source__character",
            "target",
            "target__character",
        ).prefetch_related(
            Prefetch(
                "track_progress",
                queryset=RelationshipTrackProgress.objects.select_related("track"),
                to_attr="cached_track_progress",
            ),
            Prefetch(
                "updates",
                queryset=RelationshipUpdate.objects.all(),
                to_attr="cached_updates",
            ),
            Prefetch(
                "conditions",
                queryset=RelationshipCondition.objects.all(),
                to_attr="cached_conditions",
            ),
        )

    def get_serializer_class(self):  # type: ignore[override]
        """Use list serializer for list action, full serializer for detail."""
        if self.action == "list":
            return CharacterRelationshipListSerializer
        return CharacterRelationshipSerializer


class RelationshipCapstoneViewSet(ReadOnlyModelViewSet):
    """Read-only ViewSet exposing the caller's RelationshipCapstone rows.

    Used by the frontend to populate the Soul Tether ritual perform form's
    capstone picker. The ``?other_character_sheet_id=`` filter narrows to
    capstones whose parent relationship involves a specific target character.
    """

    serializer_class = RelationshipCapstoneSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = PageNumberPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = RelationshipCapstoneFilter

    def get_queryset(self) -> RelationshipCapstone.objects.__class__:  # type: ignore[override]
        """Return capstones authored by the caller's character sheets, newest first."""
        user = self.request.user
        return (
            RelationshipCapstone.objects.filter(author__character__db_account=user)
            .select_related(
                "author",
                "author__character",
                "track",
                "relationship",
            )
            .order_by("-created_at")
        )
