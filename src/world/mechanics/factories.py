"""Factory classes for mechanics models."""

import factory
from factory.django import DjangoModelFactory

from world.mechanics.models import CharacterModifier, ModifierCategory, ModifierType


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


class CharacterModifierFactory(DjangoModelFactory):
    """Factory for creating CharacterModifier instances."""

    class Meta:
        model = CharacterModifier

    character = factory.SubFactory("evennia_extensions.factories.CharacterFactory")
    modifier_type = factory.SubFactory(ModifierTypeFactory)
    value = factory.Faker("random_int", min=-50, max=50)
