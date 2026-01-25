"""
Skills API views.
"""

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from world.skills.models import (
    PathSkillSuggestion,
    Skill,
    SkillPointBudget,
    Specialization,
)
from world.skills.serializers import (
    PathSkillSuggestionSerializer,
    SkillListSerializer,
    SkillPointBudgetSerializer,
    SkillSerializer,
    SpecializationSerializer,
)


class SkillViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for listing skills and their specializations.

    list: Get all active skills (lighter serializer without specializations)
    retrieve: Get a single skill with its specializations
    """

    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["is_active"]

    def get_queryset(self):
        """Return skills ordered by display_order."""
        queryset = Skill.objects.select_related("trait").prefetch_related("specializations")
        # Default to active only unless explicitly filtered
        if "is_active" not in self.request.query_params:
            queryset = queryset.filter(is_active=True)
        return queryset.order_by("display_order")

    def get_serializer_class(self):
        """Use lighter serializer for list, full serializer for detail."""
        if self.action == "list":
            return SkillListSerializer
        return SkillSerializer

    @action(detail=False, methods=["get"])
    def with_specializations(self, request):
        """
        Get all skills with their specializations in one request.

        This is useful for CG where we need all skills and specs upfront.
        """
        queryset = self.get_queryset()
        serializer = SkillSerializer(queryset, many=True)
        return Response(serializer.data)


class SpecializationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for listing specializations.

    Can filter by parent_skill to get specializations for a specific skill.
    """

    serializer_class = SpecializationSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["parent_skill", "is_active"]

    def get_queryset(self):
        """Return specializations ordered by parent skill and display_order."""
        queryset = Specialization.objects.select_related("parent_skill__trait")
        # Default to active only unless explicitly filtered
        if "is_active" not in self.request.query_params:
            queryset = queryset.filter(is_active=True)
        return queryset.order_by("parent_skill__display_order", "display_order")


class PathSkillSuggestionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for path skill suggestions.

    Filter by character_path to get suggestions for a specific path.
    """

    serializer_class = PathSkillSuggestionSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["character_path"]

    def get_queryset(self):
        """Return suggestions ordered by display_order."""
        return PathSkillSuggestion.objects.select_related(
            "character_path", "skill__trait"
        ).order_by("character_path", "display_order")


class SkillPointBudgetViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for skill point budget configuration.

    This is a single-row configuration model.
    """

    serializer_class = SkillPointBudgetSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Return the active budget (single row)."""
        return SkillPointBudget.objects.all()

    def list(self, request, *args, **kwargs):
        """Override list to return the single budget directly, not as array."""
        budget = SkillPointBudget.get_active_budget()
        serializer = self.get_serializer(budget)
        return Response(serializer.data)
