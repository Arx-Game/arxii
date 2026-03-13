"""Factory classes for mechanics models."""

import factory
from factory.django import DjangoModelFactory

from world.mechanics.models import (
    CharacterModifier,
    ModifierCategory,
    ModifierSource,
    ModifierTarget,
)


class ModifierCategoryFactory(DjangoModelFactory):
    """Factory for creating ModifierCategory instances."""

    class Meta:
        model = ModifierCategory
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Category{n}")
    description = factory.Faker("sentence")
    display_order = factory.Sequence(lambda n: n)


class ModifierTargetFactory(DjangoModelFactory):
    """Factory for creating ModifierTarget instances."""

    class Meta:
        model = ModifierTarget
        django_get_or_create = ("category", "name")

    name = factory.Sequence(lambda n: f"ModifierTarget{n}")
    category = factory.SubFactory(ModifierCategoryFactory)
    description = factory.Faker("sentence")
    display_order = factory.Sequence(lambda n: n)
    is_active = True


class ModifierSourceFactory(DjangoModelFactory):
    """Factory for creating ModifierSource instances.

    By default creates a source with no specific origin (unknown source).
    Use DistinctionModifierSourceFactory for sources with valid modifier_target.
    """

    class Meta:
        model = ModifierSource

    # All source fields are nullable - default is unknown source
    distinction_effect = None
    character_distinction = None


class DistinctionModifierSourceFactory(ModifierSourceFactory):
    """Factory for creating ModifierSource from a distinction.

    This creates a source with valid distinction_effect (which provides modifier_target)
    and character_distinction (for cascade deletion).
    """

    distinction_effect = factory.SubFactory("world.distinctions.factories.DistinctionEffectFactory")
    character_distinction = factory.SubFactory(
        "world.distinctions.factories.CharacterDistinctionFactory"
    )


class CharacterModifierFactory(DjangoModelFactory):
    """Factory for creating CharacterModifier instances.

    By default uses DistinctionModifierSourceFactory to ensure valid source.
    The target FK is derived from the source's distinction_effect.target.
    """

    class Meta:
        model = CharacterModifier

    character = factory.SubFactory("world.character_sheets.factories.CharacterSheetFactory")
    value = factory.Faker("random_int", min=-50, max=50)
    source = factory.SubFactory(DistinctionModifierSourceFactory)
    target = factory.LazyAttribute(lambda o: o.source.distinction_effect.target)
