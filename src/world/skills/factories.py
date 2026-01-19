"""
Factory definitions for skills system tests.

Provides efficient test data creation using factory_boy to improve
test performance and maintainability.
"""

import factory
import factory.django

from world.skills.models import (
    CharacterSkillValue,
    CharacterSpecializationValue,
    PathSkillSuggestion,
    Skill,
    SkillPointBudget,
    Specialization,
)
from world.traits.factories import TraitFactory
from world.traits.models import TraitCategory, TraitType


class SkillTraitFactory(TraitFactory):
    """Factory for creating Trait records with type SKILL."""

    trait_type = TraitType.SKILL
    category = TraitCategory.COMBAT


class SkillFactory(factory.django.DjangoModelFactory):
    """Factory for creating Skill records."""

    class Meta:
        model = Skill

    trait = factory.SubFactory(SkillTraitFactory)
    tooltip = factory.Faker("sentence")
    display_order = factory.Sequence(lambda n: n)
    is_active = True


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


class CharacterSkillValueFactory(factory.django.DjangoModelFactory):
    """Factory for creating CharacterSkillValue records."""

    class Meta:
        model = CharacterSkillValue

    character = factory.SubFactory("evennia_extensions.factories.CharacterFactory")
    skill = factory.SubFactory(SkillFactory)
    value = 20
    development_points = 0
    rust_points = 0


class CharacterSpecializationValueFactory(factory.django.DjangoModelFactory):
    """Factory for creating CharacterSpecializationValue records."""

    class Meta:
        model = CharacterSpecializationValue

    character = factory.SubFactory("evennia_extensions.factories.CharacterFactory")
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

    # NOTE: field is 'character_class' not 'path' due to SharedMemoryModel reserving 'path'
    character_class = factory.SubFactory("world.classes.factories.CharacterClassFactory")
    skill = factory.SubFactory(SkillFactory)
    suggested_value = 20
    display_order = factory.Sequence(lambda n: n)
