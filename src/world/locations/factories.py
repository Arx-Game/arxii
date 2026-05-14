import factory
import factory.django

from evennia_extensions.factories import RoomProfileFactory
from world.areas.factories import AreaFactory
from world.locations.constants import HolderType, KeyType, LocationParentType, StatKey
from world.locations.models import (
    LocationOwnership,
    LocationTenancy,
    LocationValueModifier,
    LocationValueOverride,
)
from world.scenes.factories import PersonaFactory
from world.societies.factories import OrganizationFactory


class LocationValueOverrideFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = LocationValueOverride

    parent_type = LocationParentType.AREA
    area = factory.SubFactory(AreaFactory)
    room_profile = None
    key_type = KeyType.STAT
    stat_key = StatKey.CRIME
    resonance = None
    value = 50

    class Params:
        on_room = factory.Trait(
            parent_type=LocationParentType.ROOM,
            area=None,
            room_profile=factory.SubFactory(RoomProfileFactory),
        )
        resonance_axis = factory.Trait(
            key_type=KeyType.RESONANCE,
            stat_key="",
            resonance=factory.SubFactory("world.magic.factories.ResonanceFactory"),
        )


class LocationValueModifierFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = LocationValueModifier

    parent_type = LocationParentType.AREA
    area = factory.SubFactory(AreaFactory)
    room_profile = None
    key_type = KeyType.STAT
    stat_key = StatKey.CRIME
    resonance = None
    value = 10
    change_per_day = 0
    source = ""

    class Params:
        on_room = factory.Trait(
            parent_type=LocationParentType.ROOM,
            area=None,
            room_profile=factory.SubFactory(RoomProfileFactory),
        )
        resonance_axis = factory.Trait(
            key_type=KeyType.RESONANCE,
            stat_key="",
            resonance=factory.SubFactory("world.magic.factories.ResonanceFactory"),
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
