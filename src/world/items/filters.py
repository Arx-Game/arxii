"""FilterSet classes for items API."""

import django_filters

from world.items.models import InteractionType, ItemFacet, ItemTemplate, QualityTier


class QualityTierFilter(django_filters.FilterSet):
    """Filters for QualityTier."""

    class Meta:
        model = QualityTier
        fields = ["name"]


class InteractionTypeFilter(django_filters.FilterSet):
    """Filters for InteractionType."""

    class Meta:
        model = InteractionType
        fields = ["name"]


class ItemFacetFilter(django_filters.FilterSet):
    """Filters for ItemFacet."""

    class Meta:
        model = ItemFacet
        fields = ["item_instance", "facet"]


class ItemTemplateFilter(django_filters.FilterSet):
    """Filters for ItemTemplate."""

    name = django_filters.CharFilter(lookup_expr="icontains")

    class Meta:
        model = ItemTemplate
        fields = [
            "name",
            "is_container",
            "is_stackable",
            "is_consumable",
            "is_craftable",
        ]
