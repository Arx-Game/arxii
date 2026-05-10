import factory
import factory.django

from evennia_extensions.factories import RoomProfileFactory
from world.areas.factories import AreaFactory
from world.locations.constants import LocationParentType, StatKey
from world.locations.models import LocationStatModifier, LocationStatOverride


class LocationStatOverrideFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = LocationStatOverride

    parent_type = LocationParentType.AREA
    area = factory.SubFactory(AreaFactory)
    room_profile = None
    stat_key = StatKey.CRIME
    value = 50

    class Params:
        on_room = factory.Trait(
            parent_type=LocationParentType.ROOM,
            area=None,
            room_profile=factory.SubFactory(RoomProfileFactory),
        )


class LocationStatModifierFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = LocationStatModifier

    parent_type = LocationParentType.AREA
    area = factory.SubFactory(AreaFactory)
    room_profile = None
    stat_key = StatKey.CRIME
    value = 10
    change_per_day = 0
    source = ""

    class Params:
        on_room = factory.Trait(
            parent_type=LocationParentType.ROOM,
            area=None,
            room_profile=factory.SubFactory(RoomProfileFactory),
        )
