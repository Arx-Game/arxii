"""FactoryBoy factories for the companions app (#672)."""

from __future__ import annotations

import factory
from factory.django import DjangoModelFactory

from world.companions.constants import CompanionDomain
from world.companions.models import CompanionArchetype


class CompanionArchetypeFactory(DjangoModelFactory):
    class Meta:
        model = CompanionArchetype
        django_get_or_create = ("name",)

    domain = CompanionDomain.BEAST
    name = factory.Sequence(lambda n: f"Archetype {n}")
    description = factory.Faker("sentence")
    bind_difficulty = 20
    capacity_cost = 10
