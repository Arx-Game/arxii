"""
Mechanics System Views

API viewsets for game mechanics.
"""

from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from evennia.objects.models import ObjectDB
from rest_framework import viewsets
from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated

from web.api.permissions import IsCharacterOwner
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
    ChallengeGroupSerializer,
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
from world.mechanics.services import get_available_actions
from world.mechanics.types import ChallengeGroup


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
# Available Actions
# ---------------------------------------------------------------------------


class AvailableActionsView(ListAPIView):
    """Available actions for a character at their current location.

    Returns actions grouped by challenge.
    """

    serializer_class = ChallengeGroupSerializer
    permission_classes = [IsAuthenticated, IsCharacterOwner]
    pagination_class = MechanicsPagination

    def get_queryset(self) -> list[ChallengeGroup]:
        character = get_object_or_404(ObjectDB, pk=self.kwargs["character_id"])
        location_id = self.request.query_params.get("location_id")  # noqa: USE_FILTERSET — computed view, not queryset filtering
        if location_id is not None:
            location = get_object_or_404(ObjectDB, pk=location_id)
        else:
            location = character.location
        actions = get_available_actions(character, location)
        groups: dict[int, ChallengeGroup] = {}
        for action in actions:
            cid = action.challenge_instance_id
            if cid not in groups:
                groups[cid] = ChallengeGroup(
                    challenge_instance_id=cid,
                    challenge_name=action.challenge_name,
                    actions=[],
                )
            groups[cid].actions.append(action)
        return list(groups.values())


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
