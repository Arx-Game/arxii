"""FilterSets for the tavern games API (#3292)."""

import django_filters

from world.tavern_games.models import GameSession, TavernGame


class TavernGameFilterSet(django_filters.FilterSet):
    is_active = django_filters.BooleanFilter(field_name="is_active")
    name = django_filters.CharFilter(field_name="name", lookup_expr="icontains")

    class Meta:
        model = TavernGame
        fields: list[str] = []


class GameSessionFilterSet(django_filters.FilterSet):
    place = django_filters.NumberFilter(field_name="place_id")
    # RoomProfile shares ObjectDB's pk (see CLAUDE.md) - a room id filters
    # straight through the FK, no extra join to the ObjectDB row needed.
    room = django_filters.NumberFilter(field_name="place__room_id")
    state = django_filters.CharFilter(field_name="state")

    class Meta:
        model = GameSession
        fields: list[str] = []
