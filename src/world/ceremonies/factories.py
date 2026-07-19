"""FactoryBoy factories for ceremony models (#2289)."""

import factory

from evennia_extensions.factories import RoomProfileFactory
from world.ceremonies.constants import CeremonyTypeKey
from world.ceremonies.models import (
    Ceremony,
    CeremonyHonoree,
    CeremonyType,
    SeanceManifestationOffer,
)
from world.scenes.factories import PersonaFactory
from world.worship.factories import WorshippedBeingFactory


class CeremonyTypeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CeremonyType
        django_get_or_create = ("key",)

    key = CeremonyTypeKey.FUNERAL
    name = "Funeral"
    description = "PLACEHOLDER rite copy."


class CeremonyFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Ceremony

    ceremony_type = factory.SubFactory(CeremonyTypeFactory)
    officiant = factory.SubFactory(PersonaFactory)
    being = factory.SubFactory(WorshippedBeingFactory)
    presented_being = factory.LazyAttribute(lambda o: o.being)
    location = factory.SubFactory(RoomProfileFactory)


class CeremonyHonoreeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CeremonyHonoree

    ceremony = factory.SubFactory(CeremonyFactory)


class SeanceManifestationOfferFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SeanceManifestationOffer

    ceremony_honoree = factory.SubFactory(CeremonyHonoreeFactory)
