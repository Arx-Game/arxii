"""
Classes API views.
"""

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from world.classes.models import Aspect, CharacterClass, Path
from world.classes.serializers import (
    AspectSerializer,
    CharacterClassListSerializer,
    CharacterClassSerializer,
    PathListSerializer,
    PathSerializer,
)


class PathViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for listing paths and their aspects.

    list: Get all active paths (lighter serializer without aspects)
    retrieve: Get a single path with its aspects and parent path ids
    """

    permission_classes = [IsAuthenticated]
    pagination_class = None  # Small lookup dataset
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["stage", "is_active"]

    def get_queryset(self):
        """Return paths with related data."""
        queryset = Path.objects.prefetch_related("path_aspects__aspect", "parent_paths")
        # Default to active only unless explicitly filtered
        if "is_active" not in self.request.query_params:
            queryset = queryset.filter(is_active=True)
        return queryset

    def get_serializer_class(self):
        """Use lighter serializer for list, full serializer for detail."""
        if self.action == "list":
            return PathListSerializer
        return PathSerializer


class CharacterClassViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for listing character classes.

    list: Get all visible classes (lighter serializer)
    retrieve: Get a single class with core trait ids
    """

    permission_classes = [IsAuthenticated]
    pagination_class = None  # Small lookup dataset
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["minimum_level"]

    def get_queryset(self):
        """Return visible classes with related data."""
        queryset = CharacterClass.objects.prefetch_related("core_traits")
        # Default to non-hidden only unless staff
        if not self.request.user.is_staff:
            queryset = queryset.filter(is_hidden=False)
        return queryset

    def get_serializer_class(self):
        """Use lighter serializer for list, full serializer for detail."""
        if self.action == "list":
            return CharacterClassListSerializer
        return CharacterClassSerializer


class AspectViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for listing aspects.

    Simple lookup table — no list/detail distinction needed.
    """

    serializer_class = AspectSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None  # Small lookup dataset
    queryset = Aspect.objects.all()
