"""
Mechanics System Views

API viewsets for game mechanics.
"""

from django_filters import rest_framework as filters
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
    filterset_class = ModifierTypeFilter
    pagination_class = None  # Lookup table

    def get_serializer_class(self):
        if self.action == "list":
            return ModifierTypeListSerializer
        return ModifierTypeSerializer


class CharacterModifierViewSet(viewsets.ReadOnlyModelViewSet):
    """List and retrieve character modifiers."""

    queryset = CharacterModifier.objects.select_related(
        "character", "modifier_type", "modifier_type__category"
    )
    serializer_class = CharacterModifierSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["character", "modifier_type", "modifier_type__category"]
