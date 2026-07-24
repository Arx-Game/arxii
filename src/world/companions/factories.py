"""FactoryBoy factories for the companions app (#672)."""

from __future__ import annotations

import factory
from factory.django import DjangoModelFactory

from world.companions.constants import CompanionAbilityKind, CompanionDomain
from world.companions.models import (
    Companion,
    CompanionAbility,
    CompanionAbilityFunctionTag,
    CompanionArchetype,
)
from world.magic.constants import TechniqueFunction


class CompanionArchetypeFactory(DjangoModelFactory):
    class Meta:
        model = CompanionArchetype
        django_get_or_create = ("name",)

    domain = CompanionDomain.BEAST
    name = factory.Sequence(lambda n: f"Archetype {n}")
    description = factory.Faker("sentence")
    bind_difficulty = 20
    capacity_cost = 10


class CompanionAbilityFactory(factory.django.DjangoModelFactory):
    """Factory for CompanionAbility (#1921)."""

    class Meta:
        model = CompanionAbility

    archetype = factory.SubFactory(CompanionArchetypeFactory)
    name = factory.Sequence(lambda n: f"Ability {n}")
    ability_kind = CompanionAbilityKind.ATTACK
    attack_category = "physical"


class CompanionAbilityFunctionTagFactory(factory.django.DjangoModelFactory):
    """Factory for CompanionAbilityFunctionTag (#2666)."""

    class Meta:
        model = CompanionAbilityFunctionTag

    ability = factory.SubFactory(CompanionAbilityFactory)
    function = TechniqueFunction.HOLD


class CompanionFactory(DjangoModelFactory):
    class Meta:
        model = Companion

    owner = factory.SubFactory("world.character_sheets.factories.CharacterSheetFactory")
    archetype = factory.SubFactory(CompanionArchetypeFactory)
    granting_gift = factory.SubFactory("world.magic.factories.GiftFactory")
    name = factory.Sequence(lambda n: f"Companion {n}")
