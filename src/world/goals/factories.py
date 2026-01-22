"""Factory classes for goal models."""

import factory
from factory.django import DjangoModelFactory

from world.goals.models import CharacterGoal, GoalDomain, GoalJournal, GoalRevision


class GoalDomainFactory(DjangoModelFactory):
    """Factory for creating GoalDomain instances."""

    class Meta:
        model = GoalDomain
        django_get_or_create = ("slug",)

    name = factory.Sequence(lambda n: f"Domain {n}")
    slug = factory.Sequence(lambda n: f"domain-{n}")
    description = factory.Faker("sentence")
    display_order = factory.Sequence(lambda n: n)
    is_optional = False


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
