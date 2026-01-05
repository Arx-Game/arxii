"""
Character Creation filters for ViewSets.
"""

from django.db import models
import django_filters

from world.character_sheets.models import Gender, Pronouns, Species
from world.roster.models import Family


class SpeciesFilter(django_filters.FilterSet):
    """Filter species based on heritage selection."""

    heritage_id = django_filters.CharFilter(method="filter_by_heritage")

    class Meta:
        model = Species
        fields = ["heritage_id"]

    def filter_by_heritage(self, queryset, name, value):
        """
        Filter species based on heritage_id.

        If heritage_id is provided (special heritage), return full species list.
        If not provided (normal upbringing), return human-only.
        """
        if value:
            # Special heritage = full species list (all allowed in chargen)
            return queryset
        # Normal upbringing = human-only for now
        # TODO: Make this configurable per StartingArea
        return queryset.filter(name__iexact="Human")


class FamilyFilter(django_filters.FilterSet):
    """Filter families based on starting area."""

    area_id = django_filters.CharFilter(method="filter_by_area")

    class Meta:
        model = Family
        fields = ["area_id"]

    def filter_by_area(self, queryset, name, value):
        """
        Filter families by the realm of the given starting area.

        Includes families with no origin_realm or matching the area's realm.
        """
        if not value:
            return queryset

        from world.character_creation.models import StartingArea  # noqa: PLC0415

        try:
            area = StartingArea.objects.get(id=value)
        except (StartingArea.DoesNotExist, ValueError):
            return queryset

        if area.realm:
            return queryset.filter(
                models.Q(origin_realm__isnull=True) | models.Q(origin_realm=area.realm)
            )
        return queryset


class GenderFilter(django_filters.FilterSet):
    """Filter for genders (currently no specific filters needed)."""

    class Meta:
        model = Gender
        fields = []


class PronounsFilter(django_filters.FilterSet):
    """Filter for pronouns (currently no specific filters needed)."""

    class Meta:
        model = Pronouns
        fields = []
