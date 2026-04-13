from django.db.models import QuerySet
import django_filters

from world.roster.models import Family, RosterEntry, RosterTenure, TenureGallery
from world.roster.models.families import FamilyMember


class RosterEntryFilterSet(django_filters.FilterSet):
    """Filter roster entries by related character attributes."""

    gender = django_filters.CharFilter(method="filter_gender")
    char_class = django_filters.CharFilter(method="filter_char_class")
    name = django_filters.CharFilter(
        field_name="character_sheet__character__db_key",
        lookup_expr="icontains",
    )
    roster = django_filters.NumberFilter(field_name="roster_id")

    class Meta:
        model = RosterEntry
        fields = ["gender", "char_class", "name", "roster"]

    def filter_gender(
        self, queryset: QuerySet[RosterEntry], name: str, value: str
    ) -> QuerySet[RosterEntry]:
        return queryset.filter(
            character_sheet__gender__display_name__icontains=value,
        )

    def filter_char_class(
        self, queryset: QuerySet[RosterEntry], name: str, value: str
    ) -> QuerySet[RosterEntry]:
        return queryset.filter(
            character_sheet__character__character_class_levels__character_class__name__icontains=value,
        ).distinct()


class FamilyFilterSet(django_filters.FilterSet):
    """Filter families by open positions."""

    has_open_positions = django_filters.BooleanFilter(method="filter_has_open_positions")

    class Meta:
        model = Family
        fields = ["has_open_positions"]

    def filter_has_open_positions(
        self, queryset: QuerySet[Family], name: str, value: bool
    ) -> QuerySet[Family]:
        if value:
            return queryset.filter(
                tree_members__member_type=FamilyMember.MemberType.PLACEHOLDER
            ).distinct()
        return queryset


class TenureGalleryFilterSet(django_filters.FilterSet):
    """Filter tenure galleries by tenure."""

    tenure = django_filters.NumberFilter(field_name="tenure_id")

    class Meta:
        model = TenureGallery
        fields = ["tenure"]


class RosterTenureFilterSet(django_filters.FilterSet):
    """Filter roster tenures with character name search."""

    search = django_filters.CharFilter(method="filter_search")

    class Meta:
        model = RosterTenure
        fields = ["search"]

    def filter_search(
        self, queryset: QuerySet[RosterTenure], name: str, value: str
    ) -> QuerySet[RosterTenure]:
        return queryset.filter(
            roster_entry__character_sheet__character__db_key__icontains=value,
        )
