"""
Mechanics System Views

API viewsets for game mechanics.
"""

from django.db.models import Prefetch
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated

from world.mechanics.filters import (
    ChallengeInstanceFilter,
    ChallengeTemplateFilter,
    CharacterModifierFilter,
    ModifierTargetFilter,
    SituationInstanceFilter,
    SituationTemplateFilter,
)
from world.mechanics.models import (
    ChallengeApproach,
    ChallengeInstance,
    ChallengeTemplate,
    ChallengeTemplateConsequence,
    ChallengeTemplateProperty,
    CharacterModifier,
    ModifierCategory,
    ModifierTarget,
    SituationChallengeLink,
    SituationInstance,
    SituationTemplate,
)
from world.mechanics.serializers import (
    ChallengeInstanceSerializer,
    ChallengeTemplateDetailSerializer,
    ChallengeTemplateListSerializer,
    CharacterModifierSerializer,
    ModifierCategorySerializer,
    ModifierTargetListSerializer,
    ModifierTargetSerializer,
    SituationInstanceSerializer,
    SituationTemplateDetailSerializer,
    SituationTemplateListSerializer,
)


class ModifierCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """List and retrieve modifier categories."""

    queryset = ModifierCategory.objects.all()
    serializer_class = ModifierCategorySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    pagination_class = None  # Small lookup table, no pagination needed


class ModifierTargetViewSet(viewsets.ReadOnlyModelViewSet):
    """List and retrieve modifier targets."""

    queryset = ModifierTarget.objects.select_related("category").filter(is_active=True)
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = ModifierTargetFilter
    pagination_class = None  # Lookup table

    def get_serializer_class(self):
        if self.action == "list":
            return ModifierTargetListSerializer
        return ModifierTargetSerializer


class CharacterModifierViewSet(viewsets.ReadOnlyModelViewSet):
    """List and retrieve character modifiers."""

    queryset = CharacterModifier.objects.select_related(
        "character",
        "character__character",
        "target",
        "target__category",
        "source",
        "source__distinction_effect__distinction",
    )
    serializer_class = CharacterModifierSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = CharacterModifierFilter


class MechanicsPagination(PageNumberPagination):
    """Standard pagination for mechanics endpoints."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


# ---------------------------------------------------------------------------
# Challenge & Situation ViewSets
# ---------------------------------------------------------------------------


class ChallengeTemplateViewSet(viewsets.ReadOnlyModelViewSet):
    """List and retrieve challenge templates."""

    queryset = ChallengeTemplate.objects.select_related("category").order_by("name")
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = ChallengeTemplateFilter
    pagination_class = MechanicsPagination

    def get_serializer_class(self):
        if self.action == "list":
            return ChallengeTemplateListSerializer
        return ChallengeTemplateDetailSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == "retrieve":
            qs = qs.prefetch_related(
                Prefetch(
                    "challenge_template_properties",
                    queryset=ChallengeTemplateProperty.objects.select_related("property"),
                    to_attr="cached_template_properties",
                ),
                Prefetch(
                    "approaches",
                    queryset=ChallengeApproach.objects.select_related("application", "check_type"),
                    to_attr="cached_approaches",
                ),
                Prefetch(
                    "challenge_consequences",
                    queryset=ChallengeTemplateConsequence.objects.select_related("consequence"),
                    to_attr="cached_consequences",
                ),
            )
        return qs


class ChallengeInstanceViewSet(viewsets.ReadOnlyModelViewSet):
    """List and retrieve challenge instances."""

    queryset = ChallengeInstance.objects.select_related(
        "template", "location", "target_object"
    ).order_by("-pk")
    serializer_class = ChallengeInstanceSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = ChallengeInstanceFilter
    pagination_class = MechanicsPagination


class SituationTemplateViewSet(viewsets.ReadOnlyModelViewSet):
    """List and retrieve situation templates."""

    queryset = SituationTemplate.objects.select_related("category").order_by("name")
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = SituationTemplateFilter
    pagination_class = MechanicsPagination

    def get_serializer_class(self):
        if self.action == "list":
            return SituationTemplateListSerializer
        return SituationTemplateDetailSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == "retrieve":
            qs = qs.prefetch_related(
                Prefetch(
                    "challenge_links",
                    queryset=SituationChallengeLink.objects.select_related("challenge_template"),
                    to_attr="cached_challenge_links",
                ),
            )
        return qs


class SituationInstanceViewSet(viewsets.ReadOnlyModelViewSet):
    """List and retrieve situation instances."""

    queryset = SituationInstance.objects.select_related("template", "location").order_by("-pk")
    serializer_class = SituationInstanceSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = SituationInstanceFilter
    pagination_class = MechanicsPagination
