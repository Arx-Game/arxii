"""
Character Creation filters for ViewSets.
"""

from django.db import models
from django.db.models import QuerySet
import django_filters

from world.character_sheets.models import Gender, Pronouns
from world.classes.models import Path
from world.magic.models import Gift, GlimpseTag, Technique, Tradition
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

    def filter_has_parent(
        self, queryset: QuerySet[Species], name: str, value: bool
    ) -> QuerySet[Species]:
        """Filter species that have (or don't have) a parent."""
        if value is True:
            return queryset.filter(parent__isnull=False)
        if value is False:
            return queryset.filter(parent__isnull=True)
        return queryset

    def filter_is_playable(
        self, queryset: QuerySet[Species], name: str, value: bool
    ) -> QuerySet[Species]:
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

    def filter_by_area(self, queryset: QuerySet[Family], name: str, value: str) -> QuerySet[Family]:
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


class TraditionFilter(django_filters.FilterSet):
    """Filter traditions by beginning."""

    beginning_id = django_filters.NumberFilter(field_name="beginning_traditions__beginning_id")

    class Meta:
        model = Tradition
        fields = ["beginning_id"]


class CGGiftOptionFilter(django_filters.FilterSet):
    """Declares ``draft_id`` for CG gift-options list schema/discoverability (#2426).

    Resolution (draft lookup, account scoping, tradition/path derivation) happens in
    ``CGGiftOptionViewSet.get_queryset`` — mirrors ``TraditionViewSet``'s split between
    ``_get_beginning`` (SharedMemoryModel-cache-aware resolution) and its filterset.
    """

    draft_id = django_filters.NumberFilter(method="filter_noop")

    class Meta:
        model = Gift
        fields = ["draft_id"]

    def filter_noop(self, queryset: QuerySet[Gift], name: str, value: int) -> QuerySet[Gift]:
        """No-op — the view's ``get_queryset`` already narrowed by draft_id."""
        return queryset


class CGTechniqueOptionFilter(django_filters.FilterSet):
    """Declares ``draft_id``/``gift_id`` for CG technique-options schema/discoverability.

    Resolution happens in ``CGTechniqueOptionViewSet.get_queryset`` — see
    ``CGGiftOptionFilter`` above for why.
    """

    draft_id = django_filters.NumberFilter(method="filter_noop")
    gift_id = django_filters.NumberFilter(method="filter_noop")

    class Meta:
        model = Technique
        fields = ["draft_id", "gift_id"]

    def filter_noop(
        self, queryset: QuerySet[Technique], name: str, value: int
    ) -> QuerySet[Technique]:
        """No-op — the view's ``get_queryset`` already narrowed by draft_id/gift_id."""
        return queryset


class GlimpseTagFilter(django_filters.FilterSet):
    """Filter glimpse tags by path restriction (#2611).

    ``path_id`` filters out tags whose ``paths`` M2M is non-empty and does not
    contain the given path. Tags with empty ``paths`` (the default) are always
    included. Omitting ``path_id`` returns all tags (post-CG editor mode).
    """

    path_id = django_filters.NumberFilter(method="filter_path_id")

    class Meta:
        model = GlimpseTag
        fields = ["axis", "path_id"]

    def filter_path_id(
        self, queryset: QuerySet[GlimpseTag], name: str, value: int
    ) -> QuerySet[GlimpseTag]:
        """Include tags with no path restriction OR tags restricted to this path."""
        return queryset.filter(models.Q(paths__isnull=True) | models.Q(paths=value)).distinct()
