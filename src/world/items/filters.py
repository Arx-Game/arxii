"""FilterSet classes for items API.

The item-first viewsets (``ItemFacetViewSet``, ``ItemInstanceViewSet``,
``EquippedItemViewSet``, ``OutfitViewSet``, ``OutfitSlotViewSet``) do
manual scope-param parsing in their action bodies and never call
``self.filter_queryset(...)`` — their FilterSet classes were removed
together with the dead ``filter_backends`` / ``filterset_class``
declarations. Only the catalog viewsets (QualityTier, InteractionType,
ItemTemplate) and the visible-worn endpoint still use FilterSets.
"""

import django_filters

from world.items.models import (
    EquippedItem,
    InteractionType,
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


class VisibleWornItemFilter(django_filters.FilterSet):
    """Filters for the visible-worn-items endpoint.

    The list endpoint is computed from ``visible_worn_items_for`` rather
    than queried, so this FilterSet only declares the ``character`` query
    parameter for documentation/schema purposes — the ViewSet reads the
    parameter directly. We bind it to ``EquippedItem`` (the upstream model)
    so django-filter has a real Meta.model to introspect.
    """

    character = django_filters.NumberFilter(field_name="character__id")

    class Meta:
        model = EquippedItem
        fields = ["character"]
