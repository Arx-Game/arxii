"""
Factory definitions for skills system tests.

Provides efficient test data creation using factory_boy to improve
test performance and maintainability.
"""

import factory
import factory.django

from world.skills.models import (
    CharacterSpecializationValue,
    PathSkillSuggestion,
    SkillPointBudget,
    Specialization,
    TrainingAllocation,
)
from world.traits.factories import TraitFactory
from world.traits.models import CharacterTraitValue, TraitCategory, TraitType

# Lazy factory reference (Django app_label.ModuleName.Factory), extracted to satisfy S1192.
CHARACTER_SHEET_FACTORY = "world.character_sheets.factories.CharacterSheetFactory"


class SkillFactory(TraitFactory):
    """A skill: a Trait of type SKILL (#5008)."""

    trait_type = TraitType.SKILL
    category = TraitCategory.COMBAT
    tooltip = factory.Faker("sentence")
    display_order = factory.Sequence(lambda n: n)
    is_active = True


class MagicSkillFactory(SkillFactory):
    """A Magic-category skill: the only kind a magic skill picker accepts (#4547)."""

    category = TraitCategory.MAGIC


class SpecializationFactory(factory.django.DjangoModelFactory):
    """Factory for creating Specialization records."""

    class Meta:
        model = Specialization

    name = factory.Sequence(lambda n: f"Specialization {n}")
    parent_skill = factory.SubFactory(SkillFactory)
    description = factory.Faker("paragraph")
    tooltip = factory.Faker("sentence")
    display_order = factory.Sequence(lambda n: n)
    is_active = True


class SkillRatingFactory(factory.django.DjangoModelFactory):
    """A character's rating in a skill: the skill trait's ``CharacterTraitValue`` (#5010)."""

    class Meta:
        model = CharacterTraitValue
        exclude = ("skill",)

    character = factory.SubFactory(CHARACTER_SHEET_FACTORY)
    skill = factory.SubFactory(SkillFactory)
    trait = factory.LazyAttribute(lambda o: o.skill)
    value = 20


class CharacterSpecializationValueFactory(factory.django.DjangoModelFactory):
    """Factory for creating CharacterSpecializationValue records."""

    class Meta:
        model = CharacterSpecializationValue

    character = factory.SubFactory(CHARACTER_SHEET_FACTORY)
    specialization = factory.SubFactory(SpecializationFactory)
    value = 10
    development_points = 0


class SkillPointBudgetFactory(factory.django.DjangoModelFactory):
    """Factory for creating SkillPointBudget records."""

    class Meta:
        model = SkillPointBudget

    path_points = 50
    free_points = 60
    points_per_tier = 10
    specialization_unlock_threshold = 30
    max_skill_value = 30
    max_specialization_value = 30


class PathSkillSuggestionFactory(factory.django.DjangoModelFactory):
    """Factory for creating PathSkillSuggestion records."""

    class Meta:
        model = PathSkillSuggestion

    # NOTE: field is 'character_path' not 'path' due to SharedMemoryModel reserving 'path'
    character_path = factory.SubFactory("world.classes.factories.PathFactory")
    skill = factory.SubFactory(SkillFactory)
    suggested_value = 20
    display_order = factory.Sequence(lambda n: n)


class TrainingAllocationFactory(factory.django.DjangoModelFactory):
    """Factory for creating TrainingAllocation records."""

    class Meta:
        model = TrainingAllocation

    character = factory.SubFactory(CHARACTER_SHEET_FACTORY)
    skill = factory.SubFactory(SkillFactory)
    specialization = None
    mentor = None
    ap_amount = 10
