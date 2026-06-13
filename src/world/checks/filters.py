"""Filters for the checks API."""

from __future__ import annotations

import django_filters

from world.checks.outcome_models import ConsequenceOutcome


class ConsequenceOutcomeFilter(django_filters.FilterSet):
    """Filter ConsequenceOutcome rows by character, pool, date range, and encounter."""

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
    encounter = django_filters.NumberFilter(method="filter_encounter")

    def filter_encounter(self, queryset, name, value):
        from world.combat.models import CombatEncounter  # noqa: PLC0415

        scene_id = (
            CombatEncounter.objects.filter(pk=value)
            .values_list("scene_id", flat=True)
            .first()
        )
        if scene_id is None:
            return queryset.none()
        return queryset.filter(combat_interaction__scene_id=scene_id)

    class Meta:
        model = ConsequenceOutcome
        fields = ["character", "pool", "created_after", "created_before", "encounter"]
