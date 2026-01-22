"""
Filters for distinction API ViewSets.
"""

import django_filters

from world.distinctions.models import Distinction, DistinctionCategory


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
    """

    category = django_filters.CharFilter(field_name="category__slug")
    tag = django_filters.CharFilter(field_name="tags__slug")
    cost_type = django_filters.CharFilter(method="filter_cost_type")

    class Meta:
        model = Distinction
        fields = ["category", "tag", "cost_type"]

    def filter_cost_type(self, queryset, name, value):
        """
        Filter by cost type.

        - positive: cost_per_rank > 0 (advantages that cost points)
        - negative: cost_per_rank < 0 (disadvantages that reimburse points)
        - free: cost_per_rank = 0
        """
        if value == "positive":
            return queryset.filter(cost_per_rank__gt=0)
        if value == "negative":
            return queryset.filter(cost_per_rank__lt=0)
        if value == "free":
            return queryset.filter(cost_per_rank=0)
        return queryset
