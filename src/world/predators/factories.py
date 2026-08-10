"""Factories for predator ecology tests (#3093)."""

import factory
from factory import django as factory_django

from world.areas.factories import AreaFactory
from world.predators.models import PredatorBand, PredatorKind


class PredatorKindFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = PredatorKind
        django_get_or_create = ("name",)

    name = "Bandit Company"
    base_strength = 100


class PredatorBandFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = PredatorBand

    name = factory.Sequence(lambda n: f"Test Band {n}")
    kind = factory.SubFactory(PredatorKindFactory)
    home_region = factory.SubFactory(AreaFactory)
    strength = 100
