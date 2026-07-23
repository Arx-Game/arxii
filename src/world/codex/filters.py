"""Codex filters for API endpoints."""

from django.db.models import Q
from django_filters import rest_framework as filters

from world.codex.models import CodexEntry

MIN_SEARCH_LENGTH = 2


class CodexEntryFilter(filters.FilterSet):
    """Filter codex entries by subject, category, search, and featured flag."""

    subject = filters.NumberFilter(field_name="subject_id")
    category = filters.NumberFilter(field_name="subject__category_id")
    search = filters.CharFilter(method="filter_search")
    featured = filters.BooleanFilter(method="filter_featured")

    class Meta:
        model = CodexEntry
        fields = ["subject", "category", "search", "featured"]

    def filter_search(self, queryset, name, value):
        """Search entries by name, summary, lore content, and mechanics content."""
        if not value or len(value.strip()) < MIN_SEARCH_LENGTH:
            return queryset.none() if value else queryset
        value = value.strip()
        return queryset.filter(
            Q(name__icontains=value)
            | Q(summary__icontains=value)
            | Q(lore_content__icontains=value)
            | Q(mechanics_content__icontains=value)
        )

    def filter_featured(self, queryset, name, value):
        """Filter to featured entries, ordered by featured_order."""
        if value:
            return queryset.filter(is_featured=True).order_by("featured_order")
        return queryset
