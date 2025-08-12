"""
Factory classes for classes models.
"""

import factory

from world.classes.models import CharacterClass, CharacterClassLevel


class CharacterClassFactory(factory.django.DjangoModelFactory):
    """Factory for CharacterClass."""

    class Meta:
        model = CharacterClass

    name = factory.Faker("word")
    description = factory.Faker("sentence")
    is_hidden = False
    minimum_level = factory.Faker("random_int", min=1, max=3)


class CharacterClassLevelFactory(factory.django.DjangoModelFactory):
    """Factory for CharacterClassLevel."""

    class Meta:
        model = CharacterClassLevel

    character = factory.SubFactory("evennia_extensions.factories.CharacterFactory")
    character_class = factory.SubFactory(CharacterClassFactory)
    level = factory.Faker("random_int", min=1, max=10)
    is_primary = False
