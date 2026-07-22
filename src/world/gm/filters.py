"""Filters for GM system ViewSets."""

from __future__ import annotations

from django.db.models import QuerySet
import django_filters

from world.gm.constants import GMApplicationStatus, GMTableStatus, TableRequestRole
from world.gm.models import (
    CatalogSuggestion,
    GMApplication,
    GMProfile,
    GMTable,
    GMTableMembership,
    StoryRoomGrant,
    TableUpdateRequest,
)
from world.player_submissions.constants import SubmissionStatus


class GMProfileFilter(django_filters.FilterSet):
    """Filter for GMProfile list — search by account username."""

    search = django_filters.CharFilter(
        field_name="account__username",
        lookup_expr="icontains",
        label="Search by username",
    )

    class Meta:
        model = GMProfile
        fields = ["search"]


class GMApplicationFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(choices=GMApplicationStatus.choices)
    created_after = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_before = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = GMApplication
        fields = ["status"]


class GMTableFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(choices=GMTableStatus.choices)
    gm = django_filters.NumberFilter()

    class Meta:
        model = GMTable
        fields = ["status", "gm"]


class GMTableMembershipFilter(django_filters.FilterSet):
    table = django_filters.NumberFilter()
    active = django_filters.BooleanFilter(method="filter_active")

    class Meta:
        model = GMTableMembership
        fields = ["table"]

    def filter_active(
        self, queryset: QuerySet[GMTableMembership], name: str, value: bool
    ) -> QuerySet[GMTableMembership]:
        if value:
            return queryset.filter(left_at__isnull=True)
        return queryset.filter(left_at__isnull=False)


class CatalogSuggestionFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(choices=SubmissionStatus.choices)
    proposal_kind = django_filters.CharFilter()

    class Meta:
        model = CatalogSuggestion
        fields = ["status", "proposal_kind"]


class StoryRoomGrantFilter(django_filters.FilterSet):
    """Filter for a player's own story-room grants (#2450 Fix 2) — by room."""

    room = django_filters.NumberFilter()

    class Meta:
        model = StoryRoomGrant
        fields = ["room"]


class TableUpdateRequestFilter(django_filters.FilterSet):
    """Filters for table update requests (#2631).

    ``role=mine`` narrows to the caller's own requests; ``role=gm`` to
    requests on tables the caller GMs. Without it, the viewset's base
    scoping (own ∪ GM'd) applies.
    """

    status = django_filters.CharFilter()
    kind = django_filters.CharFilter()
    role = django_filters.CharFilter(method="filter_role")

    class Meta:
        model = TableUpdateRequest
        fields = ["status", "kind"]

    def filter_role(
        self, queryset: QuerySet[TableUpdateRequest], name: str, value: str
    ) -> QuerySet[TableUpdateRequest]:
        user = self.request.user if self.request else None
        if user is None or not user.is_authenticated:
            return queryset.none()
        if value == TableRequestRole.MINE:
            return queryset.filter(membership__persona__character_sheet__character__db_account=user)
        if value == TableRequestRole.GM:
            return queryset.filter(
                membership__persona__gm_table_memberships__left_at__isnull=True,
                membership__persona__gm_table_memberships__table__gm__account=user,
            ).distinct()
        return queryset
