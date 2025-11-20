import django_filters

from world.roster.models import RosterEntry


class RosterEntryFilterSet(django_filters.FilterSet):
    """Filter roster entries by related character attributes."""

    gender = django_filters.CharFilter(method="filter_gender")
    char_class = django_filters.CharFilter(method="filter_char_class")
    name = django_filters.CharFilter(
        field_name="character__db_key",
        lookup_expr="icontains",
    )
    roster = django_filters.NumberFilter(field_name="roster_id")

    class Meta:
        model = RosterEntry
        fields = ["gender", "char_class", "name", "roster"]

    def filter_gender(self, queryset, name, value):
        return queryset.filter(
            character__db_attributes__db_key="gender",
            character__db_attributes__db_value__icontains=value,
        )

    def filter_char_class(self, queryset, name, value):
        return queryset.filter(
            character__db_attributes__db_key="class",
            character__db_attributes__db_value__icontains=value,
        )
