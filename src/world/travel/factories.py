"""Factories for the overworld travel system (#1855)."""

import factory.django

from evennia_extensions.factories import RoomProfileFactory
from world.travel.constants import TravelMode
from world.travel.models import TravelHub, TravelMethod, TravelRoute


class TravelHubFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TravelHub

    room_profile = factory.SubFactory(RoomProfileFactory)
    name = factory.Sequence(lambda n: f"Hub {n}")
    description = ""
    is_transit_stop = True
    is_active = True
    travel_modes = ["LAND"]


class TravelRouteFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TravelRoute

    origin_hub = factory.SubFactory(TravelHubFactory)
    destination_hub = factory.SubFactory(TravelHubFactory)
    distance = 100
    travel_mode = TravelMode.LAND
    is_bidirectional = True
    difficulty_modifier = 1.0
    is_active = True


class TravelMethodFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TravelMethod

    name = factory.Sequence(lambda n: f"Method {n}")
    travel_mode = TravelMode.LAND
    base_speed = 5.0
    is_default = False
