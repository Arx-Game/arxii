from django.db.models import Q, QuerySet
import django_filters

from world.roster.models import (
    Family,
    FamilyKind,
    RosterApplication,
    RosterEntry,
    RosterTenure,
    TenureGallery,
)
from world.roster.models.choices import ApplicationStatus


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
            character_sheet__character_class_levels__character_class__name__icontains=value,
        ).distinct()


class FamilyFilterSet(django_filters.FilterSet):
    """Filter families by open positions and/or starting area."""

    has_open_positions = django_filters.BooleanFilter(method="filter_has_open_positions")
    area_id = django_filters.CharFilter(method="filter_by_area")
    kind = django_filters.ModelMultipleChoiceFilter(
        field_name="kind", queryset=FamilyKind.objects.all()
    )

    class Meta:
        model = Family
        fields = ["has_open_positions", "area_id", "kind"]

    def filter_has_open_positions(
        self, queryset: QuerySet[Family], name: str, value: bool
    ) -> QuerySet[Family]:
        if value:
            return queryset.filter(
                Q(members__is_appable=True, members__sheet__isnull=True)
                | Q(kin_slot_pools__count_remaining__gt=0)
            ).distinct()
        return queryset

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
            return queryset.filter(Q(origin_realm__isnull=True) | Q(origin_realm=area.realm))
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


class RosterApplicationFilterSet(django_filters.FilterSet):
    """Filter roster applications by review status.

    The staff review queue opens on what needs action, so an omitted ``status``
    defaults to pending-only rather than showing every application ever filed.
    ``self.data`` is the raw incoming query dict django-filters hands every
    FilterSet (not a view's ``query_params``/``GET``, which this repo's
    use-filterset lint reserves views from touching directly).
    """

    status = django_filters.ChoiceFilter(choices=ApplicationStatus.choices)

    class Meta:
        model = RosterApplication
        fields = ["status"]

    @property
    def qs(self) -> QuerySet[RosterApplication]:
        queryset = super().qs
        if self.data.get("status") is None:
            queryset = queryset.filter(status=ApplicationStatus.PENDING)
        return queryset
