"""
Character Creation filters for ViewSets.
"""

from django.db import models
import django_filters

from world.character_sheets.models import Gender, Pronouns
from world.classes.models import Path
from world.roster.models import Family
from world.species.models import Species


class SpeciesFilter(django_filters.FilterSet):
    """Filter species by parent or playability."""

    parent = django_filters.NumberFilter(field_name="parent_id")
    has_parent = django_filters.BooleanFilter(method="filter_has_parent")
    is_playable = django_filters.BooleanFilter(method="filter_is_playable")

    class Meta:
        model = Species
        fields = ["parent", "has_parent", "is_playable"]

    def filter_has_parent(self, queryset, name, value):
        """Filter species that have (or don't have) a parent."""
        if value is True:
            return queryset.filter(parent__isnull=False)
        if value is False:
            return queryset.filter(parent__isnull=True)
        return queryset

    def filter_is_playable(self, queryset, name, value):
        """
        Filter species that are playable (selectable in character creation).

        A species is playable if it has no children - i.e., it's a leaf node
        in the species tree. This includes both:
        - Top-level playable species (e.g., Human with parent=null, no children)
        - Subspecies (e.g., Rex'alfar with parent=Elven, no children)
        """
        if value is True:
            return queryset.annotate(child_count=models.Count("children")).filter(child_count=0)
        if value is False:
            return queryset.annotate(child_count=models.Count("children")).filter(child_count__gt=0)
        return queryset


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


class PathFilter(django_filters.FilterSet):
    """Filter for paths in CG context (currently no specific filters needed)."""

    class Meta:
        model = Path
        fields = []
