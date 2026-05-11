import factory
import factory.django

from evennia_extensions.factories import RoomProfileFactory
from world.areas.factories import AreaFactory
from world.locations.constants import HolderType, LocationParentType, StatKey
from world.locations.models import (
    LocationOwnership,
    LocationStatModifier,
    LocationStatOverride,
    LocationTenancy,
)
from world.scenes.factories import PersonaFactory
from world.societies.factories import OrganizationFactory


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


class LocationOwnershipFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = LocationOwnership

    parent_type = LocationParentType.AREA
    area = factory.SubFactory(AreaFactory)
    room_profile = None
    holder_type = HolderType.PERSONA
    holder_persona = factory.SubFactory(PersonaFactory)
    holder_organization = None

    class Params:
        on_room = factory.Trait(
            parent_type=LocationParentType.ROOM,
            area=None,
            room_profile=factory.SubFactory(RoomProfileFactory),
        )
        on_org = factory.Trait(
            holder_type=HolderType.ORGANIZATION,
            holder_persona=None,
            holder_organization=factory.SubFactory(OrganizationFactory),
        )


class LocationTenancyFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = LocationTenancy

    parent_type = LocationParentType.ROOM
    area = None
    room_profile = factory.SubFactory(RoomProfileFactory)
    tenant_type = HolderType.PERSONA
    tenant_persona = factory.SubFactory(PersonaFactory)
    tenant_organization = None
    ends_at = None  # indefinite / revocable

    class Params:
        on_area = factory.Trait(
            parent_type=LocationParentType.AREA,
            area=factory.SubFactory(AreaFactory),
            room_profile=None,
        )
        on_org = factory.Trait(
            tenant_type=HolderType.ORGANIZATION,
            tenant_persona=None,
            tenant_organization=factory.SubFactory(OrganizationFactory),
        )
