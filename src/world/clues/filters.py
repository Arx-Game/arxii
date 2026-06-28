"""Filters for the clue read surface (#1575)."""

import django_filters

from world.clues.models import CharacterClue


class HeldClueFilter(django_filters.FilterSet):
    """Filter held clues by the holding character (always also scoped to the requester's own)."""

    character_sheet = django_filters.NumberFilter(field_name="roster_entry__character_sheet_id")

    class Meta:
        model = CharacterClue
        fields = ["character_sheet"]
