"""FactoryBoy factories for journal models."""

import factory
from factory.django import DjangoModelFactory

from world.character_sheets.factories import CharacterSheetFactory
from world.journals.constants import ResponseType
from world.journals.models import JournalEntry, JournalTag, WeeklyJournalXP


class JournalEntryFactory(DjangoModelFactory):
    """Factory for creating JournalEntry instances."""

    class Meta:
        model = JournalEntry

    author = factory.SubFactory(CharacterSheetFactory)
    title = factory.Sequence(lambda n: f"Journal Entry {n}")
    body = factory.Faker("paragraph")
    is_public = True


class PraiseFactory(JournalEntryFactory):
    """Factory for creating praise response entries."""

    parent = factory.SubFactory(JournalEntryFactory)
    response_type = ResponseType.PRAISE
    title = factory.Sequence(lambda n: f"Praise {n}")


class RetortFactory(JournalEntryFactory):
    """Factory for creating retort response entries."""

    parent = factory.SubFactory(JournalEntryFactory)
    response_type = ResponseType.RETORT
    title = factory.Sequence(lambda n: f"Retort {n}")


class JournalTagFactory(DjangoModelFactory):
    """Factory for creating JournalTag instances."""

    class Meta:
        model = JournalTag

    entry = factory.SubFactory(JournalEntryFactory)
    name = factory.Sequence(lambda n: f"tag-{n}")


class WeeklyJournalXPFactory(DjangoModelFactory):
    """Factory for creating WeeklyJournalXP instances."""

    class Meta:
        model = WeeklyJournalXP

    character_sheet = factory.SubFactory(CharacterSheetFactory)
