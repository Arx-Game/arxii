from typing import cast

from django.db.models import Q, QuerySet
import django_filters
from evennia.accounts.models import AccountDB

from world.roster.models import (
    Family,
    FamilyKind,
    RosterApplication,
    RosterEntry,
    RosterTenure,
    TenureMedia,
)
from world.roster.models.choices import ApplicationStatus
from world.roster.services.gallery import can_manage_gallery, gallery_q, hidden_ids


class RosterEntryFilterSet(django_filters.FilterSet):
    """Filter roster entries by related character attributes."""

    gender = django_filters.CharFilter(method="filter_gender")
    char_class = django_filters.CharFilter(method="filter_char_class")
    name = django_filters.CharFilter(
        field_name="character_sheet__character__db_key",
        lookup_expr="icontains",
    )
    roster = django_filters.NumberFilter(field_name="roster_id")
    realm = django_filters.CharFilter(method="filter_realm")

    class Meta:
        model = RosterEntry
        fields = ["gender", "char_class", "name", "roster", "realm"]

    def filter_realm(
        self, queryset: QuerySet[RosterEntry], name: str, value: str
    ) -> QuerySet[RosterEntry]:
        """Entries whose sheet is from the realm with this slug (#3725); unknown slug, none."""
        from world.realms.services import realm_by_slug  # noqa: PLC0415

        realm = realm_by_slug(value)
        if realm is None:
            return queryset.none()
        return queryset.filter(character_sheet__true_profile__origin_realm=realm)

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

    has_open_kin_slots = django_filters.BooleanFilter(method="filter_has_open_kin_slots")
    area_id = django_filters.CharFilter(method="filter_by_area")
    kind = django_filters.ModelMultipleChoiceFilter(
        field_name="kind", queryset=FamilyKind.objects.all()
    )

    class Meta:
        model = Family
        fields = ["has_open_kin_slots", "area_id", "kind"]

    def filter_has_open_kin_slots(
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


class GalleryPictureFilterSet(django_filters.FilterSet):
    """A character's gallery (#4151): the current player's uploads and the character's art.

    ``roster_entry`` is required; there is no "whose gallery" default. Character art the
    current player hid is left out for everyone but that player and staff.
    """

    roster_entry = django_filters.NumberFilter(method="filter_roster_entry", required=True)

    class Meta:
        model = TenureMedia
        fields = ["roster_entry"]

    def filter_roster_entry(
        self, queryset: QuerySet[TenureMedia], name: str, value: int
    ) -> QuerySet[TenureMedia]:
        entry = RosterEntry.objects.filter(pk=value).first()
        if entry is None:
            return queryset.none()
        queryset = queryset.filter(gallery_q(entry))
        if not can_manage_gallery(cast(AccountDB, self.request.user), entry):
            queryset = queryset.exclude(pk__in=hidden_ids(entry))
        return queryset
