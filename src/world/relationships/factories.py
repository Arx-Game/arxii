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
    """Factory for creating CharacterRelationship instances.

    Uses CharacterSheet instead of ObjectDB to scope relationships to tracked
    characters (PCs and NPCs with sheets) rather than all game objects.
    """

    class Meta:
        model = CharacterRelationship

    source = factory.SubFactory("world.character_sheets.factories.CharacterSheetFactory")
    target = factory.SubFactory("world.character_sheets.factories.CharacterSheetFactory")
    reputation = 0
