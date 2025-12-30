"""
Factory classes for progression models.
"""

import random

import factory
import factory.django as factory_django

from world.progression.models import (
    CharacterUnlock,
    DevelopmentPoints,
    DevelopmentTransaction,
    ExperiencePointsData,
    XPTransaction,
)
from world.progression.types import DevelopmentSource, ProgressionReason


class ExperiencePointsDataFactory(factory_django.DjangoModelFactory):
    """Factory for ExperiencePointsData."""

    class Meta:
        model = ExperiencePointsData

    account = factory.SubFactory("evennia_extensions.factories.AccountFactory")
    total_earned = factory.Faker("random_int", min=0, max=1000)
    total_spent = factory.LazyAttribute(
        lambda obj: random.randint(0, obj.total_earned),  # noqa: S311
    )


class XPTransactionFactory(factory_django.DjangoModelFactory):
    """Factory for XPTransaction."""

    class Meta:
        model = XPTransaction

    account = factory.SubFactory("evennia_extensions.factories.AccountFactory")
    amount = factory.Faker("random_int", min=-100, max=100)
    reason = factory.Faker(
        "random_element",
        elements=[choice[0] for choice in ProgressionReason.choices],
    )
    description = factory.Faker("sentence")


class DevelopmentPointsFactory(factory_django.DjangoModelFactory):
    """Factory for DevelopmentPoints."""

    class Meta:
        model = DevelopmentPoints

    character = factory.SubFactory("evennia_extensions.factories.CharacterFactory")
    trait = factory.SubFactory("world.traits.factories.TraitFactory")
    total_earned = factory.Faker("random_int", min=0, max=100)


class DevelopmentTransactionFactory(factory_django.DjangoModelFactory):
    """Factory for DevelopmentTransaction."""

    class Meta:
        model = DevelopmentTransaction

    character = factory.SubFactory("evennia_extensions.factories.CharacterFactory")
    trait = factory.SubFactory("world.traits.factories.TraitFactory")
    source = factory.Faker(
        "random_element",
        elements=[choice[0] for choice in DevelopmentSource.choices],
    )
    amount = factory.Faker("random_int", min=1, max=10)
    reason = factory.Faker(
        "random_element",
        elements=[choice[0] for choice in ProgressionReason.choices],
    )
    description = factory.Faker("sentence")


class CharacterUnlockFactory(factory_django.DjangoModelFactory):
    """Factory for CharacterUnlock."""

    class Meta:
        model = CharacterUnlock

    character = factory.SubFactory("evennia_extensions.factories.CharacterFactory")
    character_class = factory.SubFactory(
        "world.classes.factories.CharacterClassFactory",
    )
    target_level = factory.Faker("random_int", min=1, max=10)
    xp_spent = factory.Faker("random_int", min=0, max=50)
