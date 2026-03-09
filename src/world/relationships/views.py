"""API views for the relationships system."""

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ReadOnlyModelViewSet

from world.relationships.models import (
    CharacterRelationship,
    HybridRelationshipType,
    RelationshipCondition,
    RelationshipTrack,
)
from world.relationships.serializers import (
    CharacterRelationshipListSerializer,
    CharacterRelationshipSerializer,
    HybridRelationshipTypeSerializer,
    RelationshipConditionSerializer,
    RelationshipTrackSerializer,
)


class RelationshipConditionViewSet(ReadOnlyModelViewSet):
    """List and retrieve relationship conditions."""

    queryset = RelationshipCondition.objects.prefetch_related("gates_modifiers")
    serializer_class = RelationshipConditionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None


class RelationshipTrackViewSet(ReadOnlyModelViewSet):
    """List and retrieve relationship tracks with nested tiers."""

    queryset = RelationshipTrack.objects.prefetch_related("tiers")
    serializer_class = RelationshipTrackSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None


class HybridRelationshipTypeViewSet(ReadOnlyModelViewSet):
    """List and retrieve hybrid relationship types with nested requirements."""

    queryset = HybridRelationshipType.objects.prefetch_related(
        "requirements", "requirements__track"
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
            "track_progress",
            "track_progress__track",
            "updates",
            "conditions",
        )

    def get_serializer_class(self):  # type: ignore[override]
        """Use list serializer for list action, full serializer for detail."""
        if self.action == "list":
            return CharacterRelationshipListSerializer
        return CharacterRelationshipSerializer
