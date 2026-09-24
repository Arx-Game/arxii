"""Factory classes for the relationships app (#3957)."""

import factory
from factory.django import DjangoModelFactory

from world.relationships.constants import BumpValence, LabelAwareness, TypeFamily, TypeValence
from world.relationships.models import (
    CharacterRelationship,
    GrievanceOption,
    RelationshipBump,
    RelationshipCapstone,
    RelationshipCondition,
    RelationshipLabel,
    RelationshipTier,
    RelationshipType,
)

_CHARACTER_SHEET_FACTORY = "world.character_sheets.factories.CharacterSheetFactory"


class RelationshipConditionFactory(DjangoModelFactory):
    class Meta:
        model = RelationshipCondition
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Condition{n}")
    description = factory.Faker("sentence")
    display_order = factory.Sequence(lambda n: n)


class RelationshipTypeFactory(DjangoModelFactory):
    class Meta:
        model = RelationshipType
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Type{n}")
    slug = factory.LazyAttribute(lambda o: o.name.lower().replace(" ", "-"))
    description = factory.Faker("sentence")
    family = TypeFamily.COMPANY
    valence = TypeValence.NEUTRAL
    display_order = factory.Sequence(lambda n: n)


class RelationshipTierFactory(DjangoModelFactory):
    class Meta:
        model = RelationshipTier
        django_get_or_create = ("tier_number",)

    tier_number = factory.Sequence(lambda n: n + 1)
    name = factory.Sequence(lambda n: f"Tier{n + 1}")
    depth_threshold = factory.LazyAttribute(lambda o: o.tier_number * 100)
    combat_bonus = factory.LazyAttribute(lambda o: o.tier_number)


class GrievanceOptionFactory(DjangoModelFactory):
    class Meta:
        model = GrievanceOption
        django_get_or_create = ("label",)

    label = factory.Sequence(lambda n: f"Grievance {n}")
    conflict_points = 50
    display_order = factory.Sequence(lambda n: n)
    is_active = True


class CharacterRelationshipFactory(DjangoModelFactory):
    class Meta:
        model = CharacterRelationship

    source = factory.SubFactory(_CHARACTER_SHEET_FACTORY)
    target = factory.SubFactory(_CHARACTER_SHEET_FACTORY)


class RelationshipLabelFactory(DjangoModelFactory):
    class Meta:
        model = RelationshipLabel

    relationship = factory.SubFactory(CharacterRelationshipFactory)
    type = factory.SubFactory(RelationshipTypeFactory)
    awareness = LabelAwareness.PRIVATE


class RelationshipCapstoneFactory(DjangoModelFactory):
    """A ritual capstone by default (no journal entry needed); pass ``journal_entry`` otherwise."""

    class Meta:
        model = RelationshipCapstone

    relationship = factory.SubFactory(CharacterRelationshipFactory)
    tier_claimed = 1
    xp_spent = 10
    is_ritual_capstone = True


class RelationshipBumpFactory(DjangoModelFactory):
    class Meta:
        model = RelationshipBump

    relationship = factory.SubFactory(CharacterRelationshipFactory)
    interaction = factory.SubFactory("world.scenes.factories.InteractionFactory")
    timestamp = factory.LazyAttribute(lambda o: o.interaction.timestamp)
    valence = BumpValence.POSITIVE
