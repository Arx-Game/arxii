"""FactoryBoy factories for worship models (#2355)."""

import factory

from world.skills.factories import SpecializationFactory
from world.worship.models import (
    DevotionStanding,
    WorshipDeclaration,
    WorshippedBeing,
    WorshipTradition,
)


class WorshipTraditionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = WorshipTradition

    name = factory.Sequence(lambda n: f"Tradition {n}")
    description = "PLACEHOLDER tradition lore."
    rites_specialization = factory.SubFactory(SpecializationFactory)


class WorshippedBeingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = WorshippedBeing

    name = factory.Sequence(lambda n: f"Being {n}")
    description = "PLACEHOLDER being lore."
    tradition = factory.SubFactory(WorshipTraditionFactory)
    is_active = True


class DevotionStandingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = DevotionStanding

    being = factory.SubFactory(WorshippedBeingFactory)
    favor = 0
    lifetime_favor = 0


class WorshipDeclarationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = WorshipDeclaration

    public_being = factory.SubFactory(WorshippedBeingFactory)
