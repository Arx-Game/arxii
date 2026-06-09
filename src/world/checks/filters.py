"""Filters for the checks API."""

from __future__ import annotations

import django_filters

from world.checks.outcome_models import ConsequenceOutcome


class ConsequenceOutcomeFilter(django_filters.FilterSet):
    """Filter ConsequenceOutcome rows by character, pool, and date range."""

    character = django_filters.NumberFilter(field_name="character_id")
    pool = django_filters.NumberFilter(field_name="pool_id")
    created_after = django_filters.IsoDateTimeFilter(
        field_name="created_at",
        lookup_expr="gte",
    )
    created_before = django_filters.IsoDateTimeFilter(
        field_name="created_at",
        lookup_expr="lte",
    )

    class Meta:
        model = ConsequenceOutcome
        fields = ["character", "pool", "created_after", "created_before"]
