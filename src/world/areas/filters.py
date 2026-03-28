from django.db.models import QuerySet
import django_filters

from evennia_extensions.models import RoomProfile
from world.areas.models import Area, AreaClosure


class AreaFilter(django_filters.FilterSet):
    parent = django_filters.NumberFilter(field_name="parent_id")
    has_parent = django_filters.BooleanFilter(method="filter_has_parent")

    class Meta:
        model = Area
        fields = ["parent", "has_parent"]

    def filter_has_parent(self, queryset: QuerySet[Area], name: str, value: bool) -> QuerySet[Area]:
        if value is True:
            return queryset.filter(parent__isnull=False)
        if value is False:
            return queryset.filter(parent__isnull=True)
        return queryset


class RoomProfileFilter(django_filters.FilterSet):
    """Filter public rooms by area, using the closure table as a subquery."""

    area = django_filters.NumberFilter(method="filter_area")

    class Meta:
        model = RoomProfile
        fields = ["area"]

    def filter_area(
        self, queryset: QuerySet[RoomProfile], name: str, value: int
    ) -> QuerySet[RoomProfile]:
        """Return rooms in this area and all descendant areas via subquery."""
        descendant_ids = AreaClosure.objects.filter(ancestor_id=value).values("descendant_id")
        return queryset.filter(area_id__in=descendant_ids)
