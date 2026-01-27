"""Factory classes for relationships models."""

import factory
from factory.django import DjangoModelFactory

from world.relationships.models import CharacterRelationship, RelationshipCondition


class RelationshipConditionFactory(DjangoModelFactory):
    """Factory for creating RelationshipCondition instances."""

    class Meta:
        model = RelationshipCondition
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Condition{n}")
    description = factory.Faker("sentence")
    display_order = factory.Sequence(lambda n: n)


class CharacterRelationshipFactory(DjangoModelFactory):
    """Factory for creating CharacterRelationship instances."""

    class Meta:
        model = CharacterRelationship

    source = factory.SubFactory("evennia_extensions.factories.CharacterFactory")
    target = factory.SubFactory("evennia_extensions.factories.CharacterFactory")
    reputation = 0
