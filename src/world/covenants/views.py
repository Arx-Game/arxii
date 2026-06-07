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

from world.covenants.exceptions import (
    CovenantEngagementPrerequisiteNotMetError,
    SubrolePromotionError,
)
from world.covenants.filters import (
    CharacterCovenantRoleFilter,
    CovenantFilter,
    CovenantRiteFilter,
    CovenantRoleFilter,
    GearArchetypeCompatibilityFilter,
)
from world.covenants.handlers import can_engage_durance_membership
from world.covenants.models import (
    CharacterCovenantRole,
    Covenant,
    CovenantLevelThreshold,
    CovenantRite,
    CovenantRole,
    GearArchetypeCompatibility,
)
from world.covenants.permissions import IsOwnMembership
from world.covenants.serializers import (
    CharacterCovenantRoleSerializer,
    CovenantLevelThresholdSerializer,
    CovenantRiteSerializer,
    CovenantRoleSerializer,
    CovenantSerializer,
    GearArchetypeCompatibilitySerializer,
    PromoteSubroleSerializer,
)
from world.covenants.services import (
    clear_engaged_membership,
    promote_to_subrole,
    set_engaged_membership,
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

    @action(
        detail=True,
        methods=["POST"],
        permission_classes=[IsAuthenticated, IsOwnMembership],
        serializer_class=PromoteSubroleSerializer,
    )
    def promote(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/covenants/character-roles/{id}/promote/

        Promote the membership from its current parent role to a sub-role.
        Body: { "target_subrole": <pk> }

        Returns the new CharacterCovenantRole row on success.
        Returns 400 with a user_message body on promotion failures.
        """
        membership = self.get_object()
        ser = PromoteSubroleSerializer(
            data=request.data,
            context={"membership": membership},
        )
        ser.is_valid(raise_exception=True)
        try:
            new_membership = promote_to_subrole(
                membership=membership,
                target_subrole=ser.validated_data["target_subrole"],
            )
        except SubrolePromotionError as exc:
            return Response(
                {"detail": exc.user_message},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            CharacterCovenantRoleSerializer(new_membership, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )


class CovenantRoleViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only ViewSet for CovenantRole lookup data.

    Staff-authored lookup table listing available roles per covenant type.
    Supports ?covenant_type= filtering so ritual form pickers can populate
    only the roles relevant to the chosen covenant type.
    """

    serializer_class = CovenantRoleSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None  # Small lookup table — no pagination needed.
    filter_backends = [DjangoFilterBackend]
    filterset_class = CovenantRoleFilter
    queryset = CovenantRole.objects.all().order_by("covenant_type", "name")


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


class CovenantRiteViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only ViewSet for CovenantRite authored definitions.

    Rites are authored/public content — any authenticated user may read.
    No per-user scoping needed.
    """

    serializer_class = CovenantRiteSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = CovenantsPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = CovenantRiteFilter
    queryset = CovenantRite.objects.select_related("ritual", "granted_condition").all()

    def get_queryset(self) -> QuerySet[CovenantRite]:
        return CovenantRite.objects.select_related("ritual", "granted_condition").all()


class CovenantLevelThresholdViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only ViewSet for CovenantLevelThreshold authored lookup table.

    Returns the legend totals required to reach each covenant level.
    No pagination — this is a small, stable lookup table.
    """

    queryset = CovenantLevelThreshold.objects.all().order_by("level")
    serializer_class = CovenantLevelThresholdSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None  # Small lookup table — no pagination needed.
