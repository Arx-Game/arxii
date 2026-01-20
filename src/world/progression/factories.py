"""
Factory classes for progression models.
"""

import random

import factory
import factory.django as factory_django

from world.progression.models import (
    CharacterPathHistory,
    CharacterUnlock,
    DevelopmentPoints,
    DevelopmentTransaction,
    ExperiencePointsData,
    KudosClaimCategory,
    KudosPointsData,
    KudosSourceCategory,
    KudosTransaction,
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


class CharacterPathHistoryFactory(factory_django.DjangoModelFactory):
    """Factory for CharacterPathHistory."""

    class Meta:
        model = CharacterPathHistory

    character = factory.SubFactory("evennia_extensions.factories.CharacterFactory")
    path = factory.SubFactory("world.classes.factories.PathFactory")


class KudosSourceCategoryFactory(factory_django.DjangoModelFactory):
    """Factory for KudosSourceCategory."""

    class Meta:
        model = KudosSourceCategory

    name = factory.Sequence(lambda n: f"source_{n}")
    display_name = factory.LazyAttribute(lambda obj: obj.name.replace("_", " ").title())
    description = factory.Faker("sentence")
    default_amount = factory.Faker("random_int", min=1, max=10)
    is_active = True
    staff_only = False


class KudosClaimCategoryFactory(factory_django.DjangoModelFactory):
    """Factory for KudosClaimCategory."""

    class Meta:
        model = KudosClaimCategory

    name = factory.Sequence(lambda n: f"claim_{n}")
    display_name = factory.LazyAttribute(lambda obj: obj.name.replace("_", " ").title())
    description = factory.Faker("sentence")
    kudos_cost = factory.Faker("random_int", min=5, max=20)
    reward_amount = factory.Faker("random_int", min=1, max=10)
    is_active = True


class KudosPointsDataFactory(factory_django.DjangoModelFactory):
    """Factory for KudosPointsData."""

    class Meta:
        model = KudosPointsData

    account = factory.SubFactory("evennia_extensions.factories.AccountFactory")
    total_earned = factory.Faker("random_int", min=0, max=500)
    total_claimed = factory.LazyAttribute(
        lambda obj: random.randint(0, obj.total_earned),  # noqa: S311
    )


class KudosTransactionFactory(factory_django.DjangoModelFactory):
    """Factory for KudosTransaction (award type)."""

    class Meta:
        model = KudosTransaction

    account = factory.SubFactory("evennia_extensions.factories.AccountFactory")
    amount = factory.Faker("random_int", min=1, max=20)
    source_category = factory.SubFactory(KudosSourceCategoryFactory)
    claim_category = None
    description = factory.Faker("sentence")
