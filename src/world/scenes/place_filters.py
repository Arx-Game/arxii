"""Filters for place management."""

import django_filters

from world.scenes.place_models import Place


class PlaceFilter(django_filters.FilterSet):
    room = django_filters.NumberFilter(field_name="room_id")
    status = django_filters.CharFilter(field_name="status")

    class Meta:
        model = Place
        fields = ["room", "status"]
