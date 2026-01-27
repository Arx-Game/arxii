"""Factory classes for mechanics models."""

import factory
from factory.django import DjangoModelFactory

from world.mechanics.models import (
    CharacterModifier,
    ModifierCategory,
    ModifierSource,
    ModifierType,
)


class ModifierCategoryFactory(DjangoModelFactory):
    """Factory for creating ModifierCategory instances."""

    class Meta:
        model = ModifierCategory
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Category{n}")
    description = factory.Faker("sentence")
    display_order = factory.Sequence(lambda n: n)


class ModifierTypeFactory(DjangoModelFactory):
    """Factory for creating ModifierType instances."""

    class Meta:
        model = ModifierType
        django_get_or_create = ("category", "name")

    name = factory.Sequence(lambda n: f"ModifierType{n}")
    category = factory.SubFactory(ModifierCategoryFactory)
    description = factory.Faker("sentence")
    display_order = factory.Sequence(lambda n: n)
    is_active = True


class ModifierSourceFactory(DjangoModelFactory):
    """Factory for creating ModifierSource instances.

    By default creates a source with no specific origin (unknown source).
    Use specialized factories or pass explicit FKs for specific source types.
    """

    class Meta:
        model = ModifierSource

    # All source fields are nullable - default is unknown source
    distinction_effect = None
    character_distinction = None
    condition_instance = None


class DistinctionModifierSourceFactory(ModifierSourceFactory):
    """Factory for creating ModifierSource from a distinction."""

    distinction_effect = factory.SubFactory("world.distinctions.factories.DistinctionEffectFactory")
    character_distinction = factory.SubFactory(
        "world.distinctions.factories.CharacterDistinctionFactory"
    )


class CharacterModifierFactory(DjangoModelFactory):
    """Factory for creating CharacterModifier instances."""

    class Meta:
        model = CharacterModifier

    character = factory.SubFactory("world.character_sheets.factories.CharacterSheetFactory")
    modifier_type = factory.SubFactory(ModifierTypeFactory)
    value = factory.Faker("random_int", min=-50, max=50)
    source = factory.SubFactory(ModifierSourceFactory)
