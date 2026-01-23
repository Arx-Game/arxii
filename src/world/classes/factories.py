"""
Factory classes for classes models.
"""

import factory

from world.classes.models import (
    Aspect,
    CharacterClass,
    CharacterClassLevel,
    Path,
    PathAspect,
    PathStage,
)


class CharacterClassFactory(factory.django.DjangoModelFactory):
    """Factory for CharacterClass."""

    class Meta:
        model = CharacterClass

    name = factory.Sequence(lambda n: f"Class {n}")
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


class PathFactory(factory.django.DjangoModelFactory):
    """Factory for Path."""

    class Meta:
        model = Path
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Test Path {n}")
    description = factory.Faker("paragraph")
    stage = PathStage.PROSPECT
    minimum_level = 1
    is_active = True
    sort_order = 0


class AspectFactory(factory.django.DjangoModelFactory):
    """Factory for Aspect."""

    class Meta:
        model = Aspect
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Aspect {n}")
    description = factory.Faker("sentence")


class PathAspectFactory(factory.django.DjangoModelFactory):
    """Factory for PathAspect."""

    class Meta:
        model = PathAspect

    character_path = factory.SubFactory(PathFactory)
    aspect = factory.SubFactory(AspectFactory)
    weight = factory.Faker("random_int", min=1, max=3)
