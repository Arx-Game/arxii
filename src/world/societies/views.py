"""DRF viewsets for the societies membership API (#1511)."""

from __future__ import annotations

from http import HTTPMethod

from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from world.societies.filters import (
    OrganizationFilter,
    OrganizationMembershipFilter,
    OrganizationMembershipOfferFilter,
    OrganizationRankFilter,
)
from world.societies.models import (
    Organization,
    OrganizationMembership,
    OrganizationMembershipOffer,
    OrganizationRank,
    OrganizationReputation,
)
from world.societies.permissions import IsOwnMembership, active_persona_q
from world.societies.serializers import (
    OrganizationMembershipOfferSerializer,
    OrganizationMembershipSerializer,
    OrganizationRankSerializer,
    OrganizationReputationSerializer,
    OrganizationSerializer,
)
from world.tidings.serializers import PublicFeedItemSerializer


class SocietiesPagination(PageNumberPagination):
    page_size = 50


class OrganizationViewSet(viewsets.ReadOnlyModelViewSet):
    """List/retrieve organizations the requester is an active member of.

    Covenants (organizations with a related ``covenant`` row) are excluded.
    Staff see all non-covenant organizations.
    """

    # Prefetch the house-payload relations (2026-07 audit): OrganizationSerializer
    # .get_house serializes titles/domains/aspects/features inline, which fired
    # ~6 queries per org with a family (~300 on a 50-org page). select_related
    # the family + prefetch the rest so the payload reads from cache.
    queryset = (
        Organization.objects.select_related("family", "society", "org_type")
        .prefetch_related(
            "ranks",  # noqa: PREFETCH_STRING
            "titles__holder",  # noqa: PREFETCH_STRING
            "domains__holdings",  # noqa: PREFETCH_STRING
            "aspects__definition",  # noqa: PREFETCH_STRING
            "aspects__option",  # noqa: PREFETCH_STRING
            "features__feature",  # noqa: PREFETCH_STRING
            "domains__crises__crisis_type__options",  # noqa: PREFETCH_STRING — crisis cards (#2238)
            "domains__crises__chosen_option",  # noqa: PREFETCH_STRING
            "fealty__liege",  # noqa: PREFETCH_STRING  — this org's liege edge (get_house)
            "vassal_edges__vassal",  # noqa: PREFETCH_STRING  — its direct vassals
        )
        .order_by("id")
    )
    serializer_class = OrganizationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = SocietiesPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = OrganizationFilter

    def get_queryset(self):
        qs = super().get_queryset().filter(covenant__isnull=True)
        if self.request.user.is_staff:
            return qs
        return qs.filter(
            active_persona_q(self.request.user, path="memberships__persona"),
            memberships__left_at__isnull=True,
            memberships__exiled_at__isnull=True,
        ).distinct()

    @action(detail=True, methods=[HTTPMethod.POST], url_path="crisis-option")
    def crisis_option(self, request, pk=None):
        """POST /api/societies/organizations/{id}/crisis-option/ (#2238).

        The administrator's judgment call on an open DomainCrisis. Body:
        ``{"crisis": <id>, "option": <id>}``. Acts as whichever of the
        requester's personas holds domain authority (leader rank or the
        domain-steward office) — a 400 with a safe message otherwise.
        """
        from world.scenes.interaction_permissions import get_account_personas  # noqa: PLC0415
        from world.scenes.models import Persona  # noqa: PLC0415
        from world.societies.houses.crisis_services import (  # noqa: PLC0415
            CrisisServiceError,
            choose_crisis_option,
        )
        from world.societies.houses.services import can_administer_domain  # noqa: PLC0415
        from world.societies.serializers import (  # noqa: PLC0415
            CrisisOptionInputSerializer,
            _house_open_crises,
        )

        organization = self.get_object()
        ser = CrisisOptionInputSerializer(data=request.data, context={"organization": organization})
        ser.is_valid(raise_exception=True)
        crisis = ser.validated_data["crisis"]
        option = ser.validated_data["option"]

        persona = None
        owned = Persona.objects.filter(pk__in=get_account_personas(request))
        for candidate in owned:
            if can_administer_domain(candidate, crisis.domain):
                persona = candidate
                break
        if persona is None:
            return Response(
                {"detail": "You do not have authority over this domain."},
                status=400,
            )
        try:
            choose_crisis_option(crisis, persona, option)
        except CrisisServiceError as exc:
            return Response({"detail": exc.user_message}, status=400)
        return Response({"open_crises": _house_open_crises(organization)})

    @extend_schema(responses=PublicFeedItemSerializer(many=True))
    @action(detail=True, methods=[HTTPMethod.GET])
    def feed(self, request, pk=None):
        """The house feed (#1884): recent deeds + revealed scandals of the household."""
        from world.tidings.services import house_feed_for  # noqa: PLC0415

        organization = self.get_object()
        items = house_feed_for(organization)
        return Response(PublicFeedItemSerializer(items, many=True).data)


class OrganizationMembershipViewSet(viewsets.ReadOnlyModelViewSet):
    """List/retrieve memberships for personas the requester currently plays.

    Covenants (organizations with a related ``covenant`` row) are excluded.
    """

    queryset = (
        OrganizationMembership.objects.select_related("organization", "persona", "rank")
        .filter(organization__covenant__isnull=True)
        .order_by("-joined_date")
    )
    serializer_class = OrganizationMembershipSerializer
    permission_classes = [IsAuthenticated, IsOwnMembership]
    pagination_class = SocietiesPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = OrganizationMembershipFilter

    def get_queryset(self):
        qs = super().get_queryset().filter(organization__covenant__isnull=True)
        if self.request.user.is_staff:
            return qs
        return qs.filter(active_persona_q(self.request.user, path="persona"))


class OrganizationReputationViewSet(viewsets.ReadOnlyModelViewSet):
    """List/retrieve org reputations (standing) for personas the requester currently plays.

    Self-only: rows are scoped to personas the requester currently plays.
    """

    queryset = OrganizationReputation.objects.select_related("organization").order_by(
        "organization__name"
    )
    serializer_class = OrganizationReputationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = SocietiesPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ("organization",)

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(active_persona_q(self.request.user, path="persona"))


class OrganizationRankViewSet(viewsets.ReadOnlyModelViewSet):
    """List/retrieve rank ladders for organizations the requester belongs to.

    Covenants (organizations with a related ``covenant`` row) are excluded.
    Staff see all non-covenant rank ladders.
    """

    queryset = OrganizationRank.objects.select_related("organization").order_by("tier")
    serializer_class = OrganizationRankSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = SocietiesPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = OrganizationRankFilter

    def get_queryset(self):
        qs = super().get_queryset().filter(organization__covenant__isnull=True)
        if self.request.user.is_staff:
            return qs
        return qs.filter(
            active_persona_q(self.request.user, path="organization__memberships__persona"),
            organization__memberships__left_at__isnull=True,
            organization__memberships__exiled_at__isnull=True,
        ).distinct()


class OrganizationMembershipOfferViewSet(viewsets.ReadOnlyModelViewSet):
    """List/retrieve membership offers visible to the requester.

    Covenants (organizations with a related ``covenant`` row) are excluded.
    """

    queryset = OrganizationMembershipOffer.objects.select_related(
        "organization", "from_persona", "to_persona"
    ).order_by("-created_at")
    serializer_class = OrganizationMembershipOfferSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = SocietiesPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = OrganizationMembershipOfferFilter

    def get_queryset(self):
        qs = super().get_queryset().filter(organization__covenant__isnull=True)
        if self.request.user.is_staff:
            return qs
        user = self.request.user
        owned = qs.filter(active_persona_q(user, path="from_persona"))
        received = qs.filter(active_persona_q(user, path="to_persona"))
        org_visible = qs.filter(
            active_persona_q(user, path="organization__memberships__persona"),
            organization__memberships__left_at__isnull=True,
            organization__memberships__exiled_at__isnull=True,
        )
        return (owned | received | org_visible).distinct()
