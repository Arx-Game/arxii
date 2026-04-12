"""Filters for GM system ViewSets."""

from __future__ import annotations

import django_filters

from world.gm.constants import GMApplicationStatus
from world.gm.models import GMApplication


class GMApplicationFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(choices=GMApplicationStatus.choices)
    created_after = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_before = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = GMApplication
        fields = ["status"]
