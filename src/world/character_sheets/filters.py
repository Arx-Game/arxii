"""Filters for the character sheets API."""

import django_filters

from world.character_sheets.models import MoodOption


class MoodOptionFilterSet(django_filters.FilterSet):
    """Filter the moods a look can show by name."""

    name = django_filters.CharFilter(lookup_expr="icontains")

    class Meta:
        model = MoodOption
        fields = ["name"]
