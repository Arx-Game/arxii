"""DRF viewsets for the societies membership API (#1511)."""

from __future__ import annotations

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated

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
)
from world.societies.permissions import IsOwnMembership, active_persona_q
from world.societies.serializers import (
    OrganizationMembershipOfferSerializer,
    OrganizationMembershipSerializer,
    OrganizationRankSerializer,
    OrganizationSerializer,
)


class SocietiesPagination(PageNumberPagination):
    page_size = 50


class OrganizationViewSet(viewsets.ReadOnlyModelViewSet):
    """List/retrieve organizations the requester is an active member of.

    Covenants (organizations with a related ``covenant`` row) are excluded.
    Staff see all non-covenant organizations.
    """

    queryset = Organization.objects.prefetch_related(
        "ranks",  # noqa: PREFETCH_STRING
    ).order_by("id")
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
