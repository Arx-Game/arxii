"""DRF filters for the societies membership API (#1511)."""

from __future__ import annotations

import django_filters

from world.societies.models import (
    LegendEntry,
    LegendEvent,
    Organization,
    OrganizationMembership,
    OrganizationMembershipOffer,
    OrganizationRank,
    OrgAppeal,
    StandingDeclaration,
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


class StandingDeclarationFilter(django_filters.FilterSet):
    organization = django_filters.NumberFilter(field_name="organization_id")
    target_persona = django_filters.NumberFilter(field_name="target_persona_id")
    declared_by_persona = django_filters.NumberFilter(field_name="declared_by_persona_id")
    direction = django_filters.CharFilter(field_name="direction", lookup_expr="iexact")

    class Meta:
        model = StandingDeclaration
        fields = ["organization", "target_persona", "declared_by_persona", "direction"]


class OrgAppealFilter(django_filters.FilterSet):
    organization = django_filters.NumberFilter(field_name="organization_id")
    state = django_filters.CharFilter(field_name="state", lookup_expr="iexact")
    petitioner_persona = django_filters.NumberFilter(field_name="petitioner_persona_id")

    class Meta:
        model = OrgAppeal
        fields = ["organization", "state", "petitioner_persona"]


class DeedFilter(django_filters.FilterSet):
    """Filters for ``LegendEntry`` (#3466 Task 9) — the deed detail/list API."""

    persona = django_filters.NumberFilter(field_name="persona_id")
    event = django_filters.NumberFilter(field_name="event_id")

    class Meta:
        model = LegendEntry
        fields = ["persona", "event"]


class LegendEventFilter(django_filters.FilterSet):
    """Filters for ``LegendEvent`` (#3466 Task 9) — the establish-a-deed anchor API."""

    scene = django_filters.NumberFilter(field_name="scene_id")
    story = django_filters.NumberFilter(field_name="story_id")

    class Meta:
        model = LegendEvent
        fields = ["scene", "story"]
