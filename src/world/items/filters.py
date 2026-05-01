"""FilterSet classes for items API."""

import django_filters

from world.items.models import (
    EquippedItem,
    InteractionType,
    ItemFacet,
    ItemInstance,
    ItemTemplate,
    QualityTier,
)


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


class EquippedItemFilter(django_filters.FilterSet):
    """Filters for EquippedItem."""

    character = django_filters.NumberFilter(field_name="character__id")

    class Meta:
        model = EquippedItem
        fields = ["character", "body_region", "equipment_layer"]


class ItemInstanceFilter(django_filters.FilterSet):
    """Filters for ItemInstance — chiefly the character holding the item.

    ``game_object.location`` is a Python property on ObjectDB, not an ORM
    alias — at the database level the FK is named ``db_location``.
    """

    character = django_filters.NumberFilter(field_name="game_object__db_location__id")

    class Meta:
        model = ItemInstance
        fields = ["character"]


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
