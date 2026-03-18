"""API ViewSets for items."""

from django.db.models import Prefetch, QuerySet
from rest_framework import serializers, viewsets
from rest_framework.permissions import IsAuthenticated

from world.items.models import (
    InteractionType,
    ItemTemplate,
    QualityTier,
    TemplateInteraction,
    TemplateSlot,
)
from world.items.serializers import (
    InteractionTypeSerializer,
    ItemTemplateDetailSerializer,
    ItemTemplateListSerializer,
    QualityTierSerializer,
)


class QualityTierViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only ViewSet for quality tier lookup data."""

    queryset = QualityTier.objects.all()
    serializer_class = QualityTierSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None


class InteractionTypeViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only ViewSet for interaction type lookup data."""

    queryset = InteractionType.objects.order_by("label")
    serializer_class = InteractionTypeSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None


class ItemTemplateViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only ViewSet for item templates."""

    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self) -> QuerySet[ItemTemplate]:
        """Return active templates only, with prefetch for detail views."""
        qs = ItemTemplate.objects.filter(is_active=True).order_by("name")
        if self.action == "retrieve":
            qs = qs.select_related("minimum_quality_tier").prefetch_related(
                Prefetch(
                    "slots",
                    queryset=TemplateSlot.objects.all(),
                    to_attr="cached_slots",
                ),
                Prefetch(
                    "interaction_bindings",
                    queryset=TemplateInteraction.objects.select_related(
                        "interaction_type",
                    ),
                    to_attr="cached_interaction_bindings",
                ),
            )
        return qs

    def get_serializer_class(self) -> type[serializers.ModelSerializer]:
        """Use detail serializer for retrieve, list serializer for list."""
        if self.action == "retrieve":
            return ItemTemplateDetailSerializer
        return ItemTemplateListSerializer
