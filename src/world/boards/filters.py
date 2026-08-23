"""Filters for the boards API (#3286)."""

import django_filters

from world.boards.models import Board, BoardPost


class BoardFilterSet(django_filters.FilterSet):
    room_profile = django_filters.NumberFilter(field_name="room_profile_id")
    organization = django_filters.NumberFilter(field_name="organization_id")

    class Meta:
        model = Board
        fields = ["room_profile", "organization"]


class BoardPostFilterSet(django_filters.FilterSet):
    board = django_filters.NumberFilter(field_name="board_id")

    class Meta:
        model = BoardPost
        fields = ["board"]
