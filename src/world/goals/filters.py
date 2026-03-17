"""FilterSet classes for the goals app."""

import django_filters

from world.goals.models import GoalJournal


class PublicGoalJournalFilterSet(django_filters.FilterSet):
    """Filter public goal journal entries."""

    character_id = django_filters.NumberFilter(field_name="character_id")

    class Meta:
        model = GoalJournal
        fields = ["character_id"]
