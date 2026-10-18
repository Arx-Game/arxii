"""NPC-ness follows the character, not who plays it (#4418, ADR-4418)."""

from django.test import TestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import RosterEntryFactory, RosterFactory, RosterTenureFactory
from world.roster.models.choices import RosterType
from world.roster.services.activity import (
    is_player_character,
    is_story_npc,
    story_npc_sheet_ids,
)

GM_TYPECLASS = "typeclasses.gm_characters.GMCharacter"


def held_sheet(roster_type: str, *, typeclass: str | None = None, puppeted: bool = False):
    """A sheet on the given shelf with an active tenure."""
    character = CharacterFactory()
    if typeclass is not None:
        character.db_typeclass_path = typeclass
    if puppeted:
        character.db_account = AccountFactory()
    character.save()
    sheet = CharacterSheetFactory(character=character)
    entry = RosterEntryFactory(character_sheet=sheet, roster=RosterFactory(roster_type=roster_type))
    RosterTenureFactory(roster_entry=entry, end_date=None)
    return sheet


class StoryNpcRulingTests(TestCase):
    def test_played_npc_is_not_a_pc(self) -> None:
        sheet = held_sheet(RosterType.NPC, puppeted=True)
        self.assertIs(is_player_character(sheet), False)
        self.assertIs(is_story_npc(sheet), True)

    def test_pc_is_still_a_pc_offline(self) -> None:
        sheet = held_sheet(RosterType.ACTIVE)
        self.assertIsNone(sheet.character.db_account)
        self.assertIs(is_player_character(sheet), True)
        self.assertIs(is_story_npc(sheet), False)

    def test_batched_ids(self) -> None:
        npc = held_sheet(RosterType.NPC, puppeted=True)
        pc = held_sheet(RosterType.ACTIVE)
        gm = held_sheet(RosterType.NPC, typeclass=GM_TYPECLASS)
        self.assertEqual(story_npc_sheet_ids([npc.pk, pc.pk, gm.pk]), {npc.pk})


class GMCharacterStaysAPlayerCharacter(TestCase):
    def test_gm_character_on_npc_shelf(self) -> None:
        sheet = held_sheet(RosterType.NPC, typeclass=GM_TYPECLASS)
        self.assertIs(is_story_npc(sheet), False)
        self.assertIs(is_player_character(sheet), True)
