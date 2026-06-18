"""Filters for player submission ViewSets."""

import django_filters

from world.player_submissions.constants import SubmissionStatus
from world.player_submissions.models import (
    BugReport,
    PlayerFeedback,
    PlayerReport,
    SystemErrorReport,
)


class PlayerFeedbackFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(
        field_name="status",
        choices=SubmissionStatus.choices,
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
        model = PlayerFeedback
        fields = ["status"]


class BugReportFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(
        field_name="status",
        choices=SubmissionStatus.choices,
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
        model = BugReport
        fields = ["status"]


class PlayerReportFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(
        field_name="status",
        choices=SubmissionStatus.choices,
    )
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


class SystemErrorReportFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(
        field_name="status",
        choices=SubmissionStatus.choices,
    )
    exception_type = django_filters.CharFilter(
        field_name="exception_type",
        lookup_expr="icontains",
    )
    last_seen_after = django_filters.DateTimeFilter(
        field_name="last_seen",
        lookup_expr="gte",
    )
    last_seen_before = django_filters.DateTimeFilter(
        field_name="last_seen",
        lookup_expr="lte",
    )

    class Meta:
        model = SystemErrorReport
        fields = ["status", "exception_type"]
