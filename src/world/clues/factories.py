import factory
from factory.django import DjangoModelFactory

from world.clues.constants import ClueTargetKind
from world.clues.models import CharacterClue, Clue, ClueTrigger, ItemClueTrigger, RoomClue


class ClueFactory(DjangoModelFactory):
    """A codex-targeted clue by default; pass target_kind/target_* for other kinds."""

    class Meta:
        model = Clue

    target_kind = ClueTargetKind.CODEX
    target_codex_entry = factory.SubFactory("world.codex.factories.CodexEntryFactory")
    name = factory.Sequence(lambda n: f"Clue {n}")
    slug = factory.Sequence(lambda n: f"clue-{n}")
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


class ClueTriggerFactory(DjangoModelFactory):
    class Meta:
        model = ClueTrigger

    room_profile = factory.SubFactory("evennia_extensions.factories.RoomProfileFactory")
    clue = factory.SubFactory(ClueFactory)
    is_active = True


class ItemClueTriggerFactory(DjangoModelFactory):
    class Meta:
        model = ItemClueTrigger

    item_template = factory.SubFactory("world.items.factories.ItemTemplateFactory")
    clue = factory.SubFactory(ClueFactory)
    is_active = True
