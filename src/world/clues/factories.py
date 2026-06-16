import factory
from factory.django import DjangoModelFactory

from world.clues.constants import ClueTargetKind
from world.clues.models import CharacterClue, Clue


class ClueFactory(DjangoModelFactory):
    """A codex-targeted clue by default; pass target_kind/target_* for other kinds."""

    class Meta:
        model = Clue

    target_kind = ClueTargetKind.CODEX
    target_codex_entry = factory.SubFactory("world.codex.factories.CodexEntryFactory")
    name = factory.Sequence(lambda n: f"Clue {n}")
    description = "A mysterious clue."
    research_value = 1


class CharacterClueFactory(DjangoModelFactory):
    class Meta:
        model = CharacterClue

    roster_entry = factory.SubFactory("world.roster.factories.RosterEntryFactory")
    clue = factory.SubFactory(ClueFactory)
