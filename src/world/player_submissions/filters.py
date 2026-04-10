"""Filters for player submission ViewSets."""

import django_filters

from world.player_submissions.models import BugReport, PlayerFeedback, PlayerReport


class PlayerFeedbackFilter(django_filters.FilterSet):
    status = django_filters.CharFilter(field_name="status")
    created_after = django_filters.DateTimeFilter(
        field_name="created_at",
        lookup_expr="gte",
    )
    created_before = django_filters.DateTimeFilter(
        field_name="created_at",
        lookup_expr="lte",
    )

    class Meta:
        model = PlayerFeedback
        fields = ["status"]


class BugReportFilter(django_filters.FilterSet):
    status = django_filters.CharFilter(field_name="status")
    created_after = django_filters.DateTimeFilter(
        field_name="created_at",
        lookup_expr="gte",
    )
    created_before = django_filters.DateTimeFilter(
        field_name="created_at",
        lookup_expr="lte",
    )

    class Meta:
        model = BugReport
        fields = ["status"]


class PlayerReportFilter(django_filters.FilterSet):
    status = django_filters.CharFilter(field_name="status")
    reported_persona = django_filters.NumberFilter(
        field_name="reported_persona_id",
    )
    created_after = django_filters.DateTimeFilter(
        field_name="created_at",
        lookup_expr="gte",
    )
    created_before = django_filters.DateTimeFilter(
        field_name="created_at",
        lookup_expr="lte",
    )

    class Meta:
        model = PlayerReport
        fields = ["status", "reported_persona"]
