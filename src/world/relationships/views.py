"""
Relationships System Views

API viewsets for character relationships.
"""

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from world.relationships.models import CharacterRelationship, RelationshipCondition
from world.relationships.serializers import (
    CharacterRelationshipSerializer,
    RelationshipConditionSerializer,
)


class RelationshipConditionViewSet(viewsets.ReadOnlyModelViewSet):
    """List and retrieve relationship conditions."""

    queryset = RelationshipCondition.objects.prefetch_related("gates_modifiers")
    serializer_class = RelationshipConditionSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    pagination_class = None  # Small lookup table


class CharacterRelationshipViewSet(viewsets.ReadOnlyModelViewSet):
    """List and retrieve character relationships."""

    queryset = CharacterRelationship.objects.select_related(
        "source",
        "source__character",  # CharacterSheet -> ObjectDB for db_key
        "target",
        "target__character",
    ).prefetch_related("conditions")
    serializer_class = CharacterRelationshipSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["source", "target"]
