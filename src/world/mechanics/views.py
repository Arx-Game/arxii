"""
Mechanics System Views

API viewsets for game mechanics.
"""

from django_filters import rest_framework as filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from world.mechanics.models import CharacterModifier, ModifierCategory, ModifierType
from world.mechanics.serializers import (
    CharacterModifierSerializer,
    ModifierCategorySerializer,
    ModifierTypeListSerializer,
    ModifierTypeSerializer,
)


class ModifierCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """List and retrieve modifier categories."""

    queryset = ModifierCategory.objects.all()
    serializer_class = ModifierCategorySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    pagination_class = None  # Small lookup table, no pagination needed


class ModifierTypeFilter(filters.FilterSet):
    category = filters.CharFilter(field_name="category__name", lookup_expr="iexact")

    class Meta:
        model = ModifierType
        fields = ["category", "is_active"]


class ModifierTypeViewSet(viewsets.ReadOnlyModelViewSet):
    """List and retrieve modifier types."""

    queryset = ModifierType.objects.select_related("category").filter(is_active=True)
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = ModifierTypeFilter
    pagination_class = None  # Lookup table

    def get_serializer_class(self):
        if self.action == "list":
            return ModifierTypeListSerializer
        return ModifierTypeSerializer


class CharacterModifierViewSet(viewsets.ReadOnlyModelViewSet):
    """List and retrieve character modifiers.

    Note: modifier_type is a property derived from source.distinction_effect.target,
    so we select_related through that path and can only filter by character directly.
    """

    queryset = CharacterModifier.objects.select_related(
        "character",
        "character__character",  # CharacterSheet -> ObjectDB for db_key
        "source",
        "source__distinction_effect",
        "source__distinction_effect__target",
        "source__distinction_effect__target__category",
        "source__distinction_effect__distinction",
    )
    serializer_class = CharacterModifierSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    # modifier_type is a property, so we can only filter by character directly
    filterset_fields = ["character"]
