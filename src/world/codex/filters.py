"""Codex filters for API endpoints."""

from django.db.models import Case, IntegerField, OuterRef, Q, Subquery, Value, When
from django.db.models.functions import Coalesce
from django_filters import rest_framework as filters

from world.codex.models import CodexEntry, CodexEntryFiling

MIN_SEARCH_LENGTH = 2


class CodexEntryFilter(filters.FilterSet):
    """Filter codex entries by subject, category, search, and featured flag."""

    subject = filters.NumberFilter(method="filter_subject")
    category = filters.NumberFilter(field_name="subject__category_id")
    search = filters.CharFilter(method="filter_search")
    featured = filters.BooleanFilter(method="filter_featured")

    class Meta:
        model = CodexEntry
        fields = ["subject", "category", "search", "featured"]

    def filter_subject(self, queryset, name, value):
        """Return entries whose home is ``value``, plus entries filed under it.

        A canonical entry cannot also be filed under its own subject (the
        service layer rejects that filing), so the OR below never matches the
        same row twice through both halves; ``distinct()`` is kept anyway
        since the second half is a join. Canonical entries sort first, and
        filed entries follow ordered by their filing's ``sort_order``.
        """
        filing_sort_order = CodexEntryFiling.objects.filter(
            entry=OuterRef("pk"), subject_id=value
        ).values("sort_order")[:1]
        return (
            queryset.filter(Q(subject_id=value) | Q(filings__subject_id=value))
            .distinct()
            .annotate(
                is_canonical_here=Case(
                    When(subject_id=value, then=Value(0)),
                    default=Value(1),
                    output_field=IntegerField(),
                ),
                filing_sort_order=Coalesce(Subquery(filing_sort_order), Value(0)),
            )
            .order_by("is_canonical_here", "filing_sort_order", "display_order", "name")
        )

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
