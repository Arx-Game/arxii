"""API ViewSets for covenants."""

from __future__ import annotations

from django.db.models import QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from world.covenants.exceptions import CovenantEngagementPrerequisiteNotMetError
from world.covenants.filters import (
    CharacterCovenantRoleFilter,
    CovenantFilter,
    GearArchetypeCompatibilityFilter,
)
from world.covenants.handlers import can_engage_durance_membership
from world.covenants.models import CharacterCovenantRole, Covenant, GearArchetypeCompatibility
from world.covenants.permissions import IsOwnMembership
from world.covenants.serializers import (
    CharacterCovenantRoleSerializer,
    CovenantSerializer,
    GearArchetypeCompatibilitySerializer,
)
from world.covenants.services import clear_engaged_membership, set_engaged_membership


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
            "covenant",
        ).order_by("-joined_at")
        if self.request.user.is_staff:
            return qs
        # Non-staff: scope to character sheets the user currently plays.
        return qs.filter(
            character_sheet__roster_entry__tenures__end_date__isnull=True,
            character_sheet__roster_entry__tenures__player_data__account=self.request.user,
        ).distinct()

    @action(
        detail=True,
        methods=["POST"],
        permission_classes=[IsAuthenticated, IsOwnMembership],
    )
    def engage(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/covenants/character-roles/{id}/engage/

        Engage the membership for scene presence.  Returns 400 when the
        IC prerequisite is not met (no covenant members present in scene).
        """
        membership = self.get_object()
        if not can_engage_durance_membership(membership):
            return Response(
                {"detail": CovenantEngagementPrerequisiteNotMetError.user_message},
                status=status.HTTP_400_BAD_REQUEST,
            )
        set_engaged_membership(membership=membership)
        return Response(self.get_serializer(membership).data)

    @action(
        detail=True,
        methods=["POST"],
        permission_classes=[IsAuthenticated, IsOwnMembership],
    )
    def disengage(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/covenants/character-roles/{id}/disengage/

        Un-engage the membership.  Idempotent — succeeds even if not currently
        engaged.
        """
        membership = self.get_object()
        clear_engaged_membership(membership=membership)
        return Response(self.get_serializer(membership).data)


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


class CovenantViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only ViewSet for Covenant.

    Non-staff users only see covenants where they have an active membership
    on a character sheet they currently play (via the active RosterTenure
    chain). Staff see all covenants.
    """

    serializer_class = CovenantSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = CovenantsPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = CovenantFilter

    def get_queryset(self) -> QuerySet[Covenant]:
        qs = Covenant.objects.all().order_by("-formed_at")
        if self.request.user.is_staff:
            return qs
        return qs.filter(
            memberships__left_at__isnull=True,
            memberships__character_sheet__roster_entry__tenures__end_date__isnull=True,
            memberships__character_sheet__roster_entry__tenures__player_data__account=self.request.user,
        ).distinct()
