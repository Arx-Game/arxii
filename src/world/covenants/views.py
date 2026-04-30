"""API ViewSets for covenants."""

from __future__ import annotations

from django.db.models import QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated

from world.covenants.filters import CharacterCovenantRoleFilter, GearArchetypeCompatibilityFilter
from world.covenants.models import CharacterCovenantRole, GearArchetypeCompatibility
from world.covenants.serializers import (
    CharacterCovenantRoleSerializer,
    GearArchetypeCompatibilitySerializer,
)


class CovenantsPagination(PageNumberPagination):
    """Standard pagination for covenants list endpoints."""

    page_size = 50


class CharacterCovenantRoleViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only ViewSet for character covenant role assignments.

    Non-staff users only see assignments on character sheets they currently
    play (via the active RosterTenure chain). Staff see all assignments;
    they may filter explicitly by character_sheet PK to scope results.
    """

    serializer_class = CharacterCovenantRoleSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = CovenantsPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = CharacterCovenantRoleFilter

    def get_queryset(self) -> QuerySet[CharacterCovenantRole]:
        qs = CharacterCovenantRole.objects.select_related(
            "character_sheet",
            "covenant_role",
        ).order_by("-joined_at")
        if self.request.user.is_staff:
            return qs
        # Non-staff: scope to character sheets the user currently plays.
        return qs.filter(
            character_sheet__roster_entry__tenures__end_date__isnull=True,
            character_sheet__roster_entry__tenures__player_data__account=self.request.user,
        ).distinct()


class GearArchetypeCompatibilityViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only ViewSet for authored covenant×archetype compatibility rows."""

    queryset = GearArchetypeCompatibility.objects.select_related("covenant_role").order_by(
        "covenant_role__name",
        "gear_archetype",
    )
    serializer_class = GearArchetypeCompatibilitySerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None  # Authored lookup table — small, no pagination needed.
    filter_backends = [DjangoFilterBackend]
    filterset_class = GearArchetypeCompatibilityFilter
