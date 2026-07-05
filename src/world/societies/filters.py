"""DRF filters for the societies membership API (#1511)."""

from __future__ import annotations

import django_filters

from world.societies.models import (
    Organization,
    OrganizationMembership,
    OrganizationMembershipOffer,
    OrganizationRank,
)


class OrganizationFilter(django_filters.FilterSet):
    society = django_filters.CharFilter(field_name="society__name", lookup_expr="iexact")
    org_type = django_filters.CharFilter(field_name="org_type__name", lookup_expr="iexact")
    name = django_filters.CharFilter(field_name="name", lookup_expr="iexact")

    class Meta:
        model = Organization
        fields = ["society", "org_type", "name"]


class OrganizationMembershipFilter(django_filters.FilterSet):
    organization = django_filters.NumberFilter(field_name="organization_id")
    is_active = django_filters.BooleanFilter(method="filter_is_active")

    class Meta:
        model = OrganizationMembership
        fields = ["organization", "is_active"]

    def filter_is_active(
        self,
        queryset,
        name: str,
        value: bool,
    ):
        if value:
            return queryset.filter(left_at__isnull=True, exiled_at__isnull=True)
        return queryset.exclude(left_at__isnull=True, exiled_at__isnull=True)


class OrganizationRankFilter(django_filters.FilterSet):
    organization = django_filters.NumberFilter(field_name="organization_id")

    class Meta:
        model = OrganizationRank
        fields = ["organization"]


class OrganizationMembershipOfferFilter(django_filters.FilterSet):
    organization = django_filters.NumberFilter(field_name="organization_id")
    kind = django_filters.CharFilter(field_name="kind", lookup_expr="iexact")
    status = django_filters.CharFilter(field_name="status", lookup_expr="iexact")
    to_persona = django_filters.NumberFilter(field_name="to_persona_id")
    from_persona = django_filters.NumberFilter(field_name="from_persona_id")

    class Meta:
        model = OrganizationMembershipOffer
        fields = ["organization", "kind", "status", "to_persona", "from_persona"]
