from django.db.models import QuerySet
import django_filters

from world.areas.models import Area


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
