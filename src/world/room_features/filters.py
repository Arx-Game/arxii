"""Filters for the room_features web surfaces.

Mirrors ``world.items.filters.LabStationFilter``'s shape (#1234 whole-branch
review) -- each filter lets a caller scope a defense-status list endpoint to
a single exit or room rather than listing every installation in the game
(#2177 whole-branch review, Important #4).
"""

from __future__ import annotations

import django_filters

from world.room_features.models import ExitBarsDetails, RoomAlarmDetails, RoomWardDetails


class ExitBarsFilter(django_filters.FilterSet):
    """Scope the bars-status list to a single exit."""

    exit_profile = django_filters.NumberFilter(field_name="exit_profile_id")

    class Meta:
        model = ExitBarsDetails
        fields = ["exit_profile"]


class RoomWardFilter(django_filters.FilterSet):
    """Scope the ward-status list to a single room."""

    room_profile = django_filters.NumberFilter(field_name="room_profile_id")

    class Meta:
        model = RoomWardDetails
        fields = ["room_profile"]


class RoomAlarmFilter(django_filters.FilterSet):
    """Scope the alarm-status list to a single room."""

    room_profile = django_filters.NumberFilter(field_name="room_profile_id")

    class Meta:
        model = RoomAlarmDetails
        fields = ["room_profile"]
