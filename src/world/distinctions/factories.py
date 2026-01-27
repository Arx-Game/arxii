"""Factory classes for distinction models."""

import factory
from factory.django import DjangoModelFactory

from world.distinctions.models import (
    CharacterDistinction,
    CharacterDistinctionOther,
    Distinction,
    DistinctionCategory,
    DistinctionEffect,
    DistinctionPrerequisite,
    DistinctionTag,
)
from world.distinctions.types import DistinctionOrigin


class DistinctionCategoryFactory(DjangoModelFactory):
    """Factory for creating DistinctionCategory instances."""

    class Meta:
        model = DistinctionCategory
        django_get_or_create = ("slug",)

    name = factory.Sequence(lambda n: f"Category {n}")
    slug = factory.Sequence(lambda n: f"category-{n}")
    description = factory.Faker("sentence")
    display_order = factory.Sequence(lambda n: n)


class DistinctionTagFactory(DjangoModelFactory):
    """Factory for creating DistinctionTag instances."""

    class Meta:
        model = DistinctionTag
        django_get_or_create = ("slug",)

    name = factory.Sequence(lambda n: f"Tag {n}")
    slug = factory.Sequence(lambda n: f"tag-{n}")


class DistinctionFactory(DjangoModelFactory):
    """Factory for creating Distinction instances."""

    class Meta:
        model = Distinction
        django_get_or_create = ("slug",)

    name = factory.Sequence(lambda n: f"Distinction {n}")
    slug = factory.Sequence(lambda n: f"distinction-{n}")
    description = factory.Faker("paragraph")
    category = factory.SubFactory(DistinctionCategoryFactory)
    cost_per_rank = 1
    max_rank = 1


class DistinctionEffectFactory(DjangoModelFactory):
    """Factory for creating DistinctionEffect instances."""

    class Meta:
        model = DistinctionEffect

    distinction = factory.SubFactory(DistinctionFactory)
    target = factory.SubFactory("world.mechanics.factories.ModifierTypeFactory")
    value_per_rank = 5
    description = factory.Faker("sentence")


class DistinctionPrerequisiteFactory(DjangoModelFactory):
    """Factory for creating DistinctionPrerequisite instances."""

    class Meta:
        model = DistinctionPrerequisite

    distinction = factory.SubFactory(DistinctionFactory)
    rule_json = {"type": "species", "operator": "is", "value": "human"}
    description = factory.Faker("sentence")


class CharacterDistinctionFactory(DjangoModelFactory):
    """Factory for creating CharacterDistinction instances."""

    class Meta:
        model = CharacterDistinction

    character = factory.SubFactory("evennia_extensions.factories.CharacterFactory")
    distinction = factory.SubFactory(DistinctionFactory)
    rank = 1
    origin = DistinctionOrigin.CHARACTER_CREATION


class CharacterDistinctionOtherFactory(DjangoModelFactory):
    """Factory for creating CharacterDistinctionOther instances."""

    class Meta:
        model = CharacterDistinctionOther

    character = factory.SubFactory("evennia_extensions.factories.CharacterFactory")
    parent_distinction = factory.SubFactory(DistinctionFactory, allow_other=True)
    freeform_text = factory.Faker("word")
