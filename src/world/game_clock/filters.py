"""Filters for the game clock REST API."""

import django_filters

from world.game_clock.constants import ClockChange
from world.game_clock.models import GameClockHistory


class ClockHistoryFilter(django_filters.FilterSet):
    """Narrow the clock's history to one kind of change (#5248)."""

    change = django_filters.ChoiceFilter(choices=ClockChange.choices)

    class Meta:
        model = GameClockHistory
        fields = ["change"]
