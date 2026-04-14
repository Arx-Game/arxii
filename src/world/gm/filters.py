"""Filters for GM system ViewSets."""

from __future__ import annotations

from django.db.models import QuerySet
import django_filters

from world.gm.constants import GMApplicationStatus, GMTableStatus
from world.gm.models import GMApplication, GMTable, GMTableMembership


class GMApplicationFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(choices=GMApplicationStatus.choices)
    created_after = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_before = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = GMApplication
        fields = ["status"]


class GMTableFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(choices=GMTableStatus.choices)
    gm = django_filters.NumberFilter()

    class Meta:
        model = GMTable
        fields = ["status", "gm"]


class GMTableMembershipFilter(django_filters.FilterSet):
    table = django_filters.NumberFilter()
    active = django_filters.BooleanFilter(method="filter_active")

    class Meta:
        model = GMTableMembership
        fields = ["table"]

    def filter_active(
        self, queryset: QuerySet[GMTableMembership], name: str, value: bool
    ) -> QuerySet[GMTableMembership]:
        if value:
            return queryset.filter(left_at__isnull=True)
        return queryset.filter(left_at__isnull=False)
