"""Factory classes for codex models."""

import factory
from factory.django import DjangoModelFactory

from world.codex.models import (
    BeginningsCodexGrant,
    CharacterClueKnowledge,
    CharacterCodexKnowledge,
    CodexCategory,
    CodexClue,
    CodexEntry,
    CodexSubject,
    CodexTeachingOffer,
    DistinctionCodexGrant,
    PathCodexGrant,
)


class CodexCategoryFactory(DjangoModelFactory):
    """Factory for creating CodexCategory instances."""

    class Meta:
        model = CodexCategory
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Category {n}")
    description = factory.Faker("sentence")
    display_order = factory.Sequence(lambda n: n)


class CodexSubjectFactory(DjangoModelFactory):
    """Factory for creating CodexSubject instances."""

    class Meta:
        model = CodexSubject

    category = factory.SubFactory(CodexCategoryFactory)
    parent = None
    name = factory.Sequence(lambda n: f"Subject {n}")
    description = factory.Faker("sentence")
    display_order = factory.Sequence(lambda n: n)


class CodexEntryFactory(DjangoModelFactory):
    """Factory for creating CodexEntry instances."""

    class Meta:
        model = CodexEntry

    subject = factory.SubFactory(CodexSubjectFactory)
    name = factory.Sequence(lambda n: f"Entry {n}")
    lore_content = factory.Faker("paragraph")
    share_cost = 5
    learn_cost = 5
    learn_difficulty = 10
    learn_threshold = 10
    display_order = factory.Sequence(lambda n: n)


class CodexClueFactory(DjangoModelFactory):
    """Factory for creating CodexClue instances."""

    class Meta:
        model = CodexClue

    entry = factory.SubFactory(CodexEntryFactory)
    name = factory.Sequence(lambda n: f"Clue {n}")
    description = "A mysterious clue."
    research_value = 1


class CharacterClueKnowledgeFactory(DjangoModelFactory):
    """Factory for creating CharacterClueKnowledge instances."""

    class Meta:
        model = CharacterClueKnowledge

    roster_entry = factory.SubFactory("world.roster.factories.RosterEntryFactory")
    clue = factory.SubFactory(CodexClueFactory)


class CharacterCodexKnowledgeFactory(DjangoModelFactory):
    """Factory for creating CharacterCodexKnowledge instances."""

    class Meta:
        model = CharacterCodexKnowledge

    roster_entry = factory.SubFactory("world.roster.factories.RosterEntryFactory")
    entry = factory.SubFactory(CodexEntryFactory)
    status = CharacterCodexKnowledge.Status.UNCOVERED
    learning_progress = 0


class CodexTeachingOfferFactory(DjangoModelFactory):
    """Factory for creating CodexTeachingOffer instances."""

    class Meta:
        model = CodexTeachingOffer

    teacher = factory.SubFactory("world.roster.factories.RosterTenureFactory")
    entry = factory.SubFactory(CodexEntryFactory)
    pitch = factory.Faker("paragraph")
    gold_cost = 0
    banked_ap = 5


class BeginningsCodexGrantFactory(DjangoModelFactory):
    """Factory for creating BeginningsCodexGrant instances."""

    class Meta:
        model = BeginningsCodexGrant

    beginnings = factory.SubFactory("world.character_creation.factories.BeginningsFactory")
    entry = factory.SubFactory(CodexEntryFactory)


class PathCodexGrantFactory(DjangoModelFactory):
    """Factory for creating PathCodexGrant instances."""

    class Meta:
        model = PathCodexGrant

    path = factory.SubFactory("world.classes.factories.PathFactory")
    entry = factory.SubFactory(CodexEntryFactory)


class DistinctionCodexGrantFactory(DjangoModelFactory):
    """Factory for creating DistinctionCodexGrant instances."""

    class Meta:
        model = DistinctionCodexGrant

    distinction = factory.SubFactory("world.distinctions.factories.DistinctionFactory")
    entry = factory.SubFactory(CodexEntryFactory)
