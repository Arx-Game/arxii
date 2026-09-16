"""FilterSets for the worship API."""

from __future__ import annotations

from django.db.models import Q, QuerySet
import django_filters

from world.worship.constants import BeingVisibility
from world.worship.models import WorshippedBeing


class StaffBeingFilterSet(django_filters.FilterSet):
    """The Deity Editor's list filters (#3780). ``visibility`` reads the Codex tier
    the way ``editor_services.visibility_of`` does, as one query."""

    visibility = django_filters.ChoiceFilter(
        choices=BeingVisibility.choices, method="filter_visibility"
    )

    class Meta:
        model = WorshippedBeing
        fields = ["tradition", "is_active", "visibility"]

    def filter_visibility(
        self, queryset: QuerySet[WorshippedBeing], name: str, value: str
    ) -> QuerySet[WorshippedBeing]:
        if value == BeingVisibility.PUBLIC:
            return queryset.filter(codex_entry__is_public=True)
        if value == BeingVisibility.OBSCURE:
            return queryset.filter(
                codex_entry__is_public=False, codex_entry__organization_grants__isnull=False
            )
        if value == BeingVisibility.SECRET:
            return queryset.filter(
                Q(codex_entry__isnull=True)
                | Q(codex_entry__is_public=False, codex_entry__organization_grants__isnull=True)
            )
        return queryset
