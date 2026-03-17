"""Filters for the journal system API."""

import django_filters

from world.journals.models import JournalEntry


class JournalEntryFilter(django_filters.FilterSet):
    """Filter for JournalEntry list views."""

    author = django_filters.NumberFilter(field_name="author_id")
    tag = django_filters.CharFilter(field_name="tags__name")

    class Meta:
        model = JournalEntry
        fields = ["author", "tag"]
