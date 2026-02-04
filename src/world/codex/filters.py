"""Codex filters for API endpoints."""

from django.db.models import Q
from django_filters import rest_framework as filters

from world.codex.models import CodexEntry

MIN_SEARCH_LENGTH = 2


class CodexEntryFilter(filters.FilterSet):
    """Filter codex entries by subject, category, and search text."""

    subject = filters.NumberFilter(field_name="subject_id")
    category = filters.NumberFilter(field_name="subject__category_id")
    search = filters.CharFilter(method="filter_search")

    class Meta:
        model = CodexEntry
        fields = ["subject", "category", "search"]

    def filter_search(self, queryset, name, value):
        """Search entries by name, summary, and content."""
        if not value or len(value.strip()) < MIN_SEARCH_LENGTH:
            return queryset.none() if value else queryset
        value = value.strip()
        return queryset.filter(
            Q(name__icontains=value) | Q(summary__icontains=value) | Q(content__icontains=value)
        )
