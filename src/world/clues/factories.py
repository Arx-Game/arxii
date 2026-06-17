import factory
from factory.django import DjangoModelFactory

from world.clues.constants import ClueTargetKind
from world.clues.models import CharacterClue, Clue, RoomClue


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


class RoomClueFactory(DjangoModelFactory):
    class Meta:
        model = RoomClue

    room_profile = factory.SubFactory("evennia_extensions.factories.RoomProfileFactory")
    clue = factory.SubFactory(ClueFactory)
    detect_difficulty = 0
    is_active = True
