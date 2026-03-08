"""Factory classes for relationships models."""

import factory
from factory.django import DjangoModelFactory

from world.relationships.constants import TrackSign
from world.relationships.models import (
    CharacterRelationship,
    HybridRelationshipType,
    HybridRequirement,
    RelationshipChange,
    RelationshipCondition,
    RelationshipTier,
    RelationshipTrack,
    RelationshipTrackProgress,
    RelationshipUpdate,
)


class RelationshipConditionFactory(DjangoModelFactory):
    """Factory for creating RelationshipCondition instances."""

    class Meta:
        model = RelationshipCondition
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Condition{n}")
    description = factory.Faker("sentence")
    display_order = factory.Sequence(lambda n: n)


class RelationshipTrackFactory(DjangoModelFactory):
    """Factory for creating RelationshipTrack instances."""

    class Meta:
        model = RelationshipTrack
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Track{n}")
    slug = factory.LazyAttribute(lambda o: o.name.lower().replace(" ", "-"))
    description = factory.Faker("sentence")
    sign = TrackSign.POSITIVE
    display_order = factory.Sequence(lambda n: n)


class RelationshipTierFactory(DjangoModelFactory):
    """Factory for creating RelationshipTier instances."""

    class Meta:
        model = RelationshipTier

    track = factory.SubFactory(RelationshipTrackFactory)
    name = factory.Sequence(lambda n: f"Tier{n}")
    tier_number = factory.Sequence(lambda n: n)
    point_threshold = factory.LazyAttribute(lambda o: o.tier_number * 10)
    description = factory.Faker("sentence")
    mechanical_bonus_description = ""


class HybridRelationshipTypeFactory(DjangoModelFactory):
    """Factory for creating HybridRelationshipType instances."""

    class Meta:
        model = HybridRelationshipType
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"HybridType{n}")
    slug = factory.LazyAttribute(lambda o: o.name.lower().replace(" ", "-"))
    description = factory.Faker("sentence")
    mechanical_bonus_description = ""


class HybridRequirementFactory(DjangoModelFactory):
    """Factory for creating HybridRequirement instances."""

    class Meta:
        model = HybridRequirement

    hybrid_type = factory.SubFactory(HybridRelationshipTypeFactory)
    track = factory.SubFactory(RelationshipTrackFactory)
    minimum_tier = 1


class CharacterRelationshipFactory(DjangoModelFactory):
    """Factory for creating CharacterRelationship instances."""

    class Meta:
        model = CharacterRelationship

    source = factory.SubFactory("world.character_sheets.factories.CharacterSheetFactory")
    target = factory.SubFactory("world.character_sheets.factories.CharacterSheetFactory")


class RelationshipTrackProgressFactory(DjangoModelFactory):
    """Factory for creating RelationshipTrackProgress instances."""

    class Meta:
        model = RelationshipTrackProgress

    relationship = factory.SubFactory(CharacterRelationshipFactory)
    track = factory.SubFactory(RelationshipTrackFactory)
    points = 0


class RelationshipUpdateFactory(DjangoModelFactory):
    """Factory for creating RelationshipUpdate instances."""

    class Meta:
        model = RelationshipUpdate

    relationship = factory.SubFactory(CharacterRelationshipFactory)
    author = factory.SubFactory("world.character_sheets.factories.CharacterSheetFactory")
    title = factory.Faker("sentence", nb_words=4)
    writeup = factory.Faker("paragraph")
    track = factory.SubFactory(RelationshipTrackFactory)
    points_earned = 5


class RelationshipChangeFactory(DjangoModelFactory):
    """Factory for creating RelationshipChange instances."""

    class Meta:
        model = RelationshipChange

    relationship = factory.SubFactory(CharacterRelationshipFactory)
    author = factory.SubFactory("world.character_sheets.factories.CharacterSheetFactory")
    title = factory.Faker("sentence", nb_words=4)
    writeup = factory.Faker("paragraph")
    source_track = factory.SubFactory(RelationshipTrackFactory)
    target_track = factory.SubFactory(RelationshipTrackFactory)
    points_moved = 5
