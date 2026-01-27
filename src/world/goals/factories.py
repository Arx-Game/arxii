"""Factory classes for goal models."""

import factory
from factory.django import DjangoModelFactory

from world.goals.models import CharacterGoal, GoalJournal, GoalRevision
from world.mechanics.factories import ModifierCategoryFactory, ModifierTypeFactory


class GoalDomainFactory(ModifierTypeFactory):
    """Factory for creating goal domain ModifierType instances.

    Goal domains are ModifierType entries with category='goal'.
    This factory creates them with appropriate defaults.
    """

    name = factory.Sequence(lambda n: f"Domain {n}")
    category = factory.LazyAttribute(lambda _: ModifierCategoryFactory(name="goal"))
    description = factory.Faker("sentence")
    display_order = factory.Sequence(lambda n: n)


class CharacterGoalFactory(DjangoModelFactory):
    """Factory for creating CharacterGoal instances."""

    class Meta:
        model = CharacterGoal

    character = factory.SubFactory("evennia_extensions.factories.CharacterFactory")
    domain = factory.SubFactory(GoalDomainFactory)
    points = 10
    notes = factory.Faker("sentence")


class GoalJournalFactory(DjangoModelFactory):
    """Factory for creating GoalJournal instances."""

    class Meta:
        model = GoalJournal

    character = factory.SubFactory("evennia_extensions.factories.CharacterFactory")
    domain = factory.SubFactory(GoalDomainFactory)
    title = factory.Faker("sentence", nb_words=4)
    content = factory.Faker("paragraph")
    is_public = False
    xp_awarded = 0


class GoalRevisionFactory(DjangoModelFactory):
    """Factory for creating GoalRevision instances."""

    class Meta:
        model = GoalRevision

    character = factory.SubFactory("evennia_extensions.factories.CharacterFactory")
