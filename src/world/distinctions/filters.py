"""
Filters for distinction API ViewSets.
"""

from django.db.models import Q
import django_filters

from world.distinctions.models import Distinction, DistinctionCategory

# Constants for cost_type filter values
COST_TYPE_POSITIVE = "positive"
COST_TYPE_NEGATIVE = "negative"
COST_TYPE_FREE = "free"


class DistinctionCategoryFilter(django_filters.FilterSet):
    """Filter for DistinctionCategory (currently no specific filters needed)."""

    class Meta:
        model = DistinctionCategory
        fields = []


class DistinctionFilter(django_filters.FilterSet):
    """
    Filter for Distinction listings.

    Supports filtering by:
    - category: Category slug
    - tag: Tag slug (filter distinctions that have this tag)
    - cost_type: "positive" (advantages), "negative" (disadvantages), "free"
    - search: Search name, description, tags, and effect descriptions
    - exclude_variants: Exclude variant distinctions (show only parents/standalone)
    """

    category = django_filters.CharFilter(field_name="category__slug")
    tag = django_filters.CharFilter(field_name="tags__slug")
    cost_type = django_filters.CharFilter(method="filter_cost_type")
    search = django_filters.CharFilter(method="filter_search")
    exclude_variants = django_filters.BooleanFilter(method="filter_exclude_variants")

    class Meta:
        model = Distinction
        fields = ["category", "tag", "cost_type", "search", "exclude_variants"]

    def filter_cost_type(self, queryset, name, value):
        """
        Filter by cost type.

        - positive: cost_per_rank > 0 (advantages that cost points)
        - negative: cost_per_rank < 0 (disadvantages that reimburse points)
        - free: cost_per_rank = 0
        """
        if value == COST_TYPE_POSITIVE:
            return queryset.filter(cost_per_rank__gt=0)
        if value == COST_TYPE_NEGATIVE:
            return queryset.filter(cost_per_rank__lt=0)
        if value == COST_TYPE_FREE:
            return queryset.filter(cost_per_rank=0)
        return queryset

    def filter_search(self, queryset, name, value):
        """Search across name, description, tags, and effect descriptions."""
        if not value:
            return queryset
        return queryset.filter(
            Q(name__icontains=value)
            | Q(description__icontains=value)
            | Q(tags__name__icontains=value)
            | Q(effects__description__icontains=value)
        ).distinct()

    def filter_exclude_variants(self, queryset, name, value):
        """Exclude variant distinctions, showing only parents and standalone."""
        if value:
            return queryset.filter(parent_distinction__isnull=True)
        return queryset
