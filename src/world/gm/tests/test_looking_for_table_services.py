"""Tests for the looking-for-table service layer (#2431)."""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.factories import GMTableFactory
from world.gm.services import join_table, set_looking_for_table
from world.roster.factories import (
    PlayerDataFactory,
    RosterEntryFactory,
    RosterTenureFactory,
)
from world.scenes.factories import PersonaFactory


def _make_persona_with_player_data(player_data):
    """Build a persona with a full roster_entry → tenure → player_data chain."""
    char = CharacterFactory()
    sheet = CharacterSheetFactory(character=char)
    roster_entry = RosterEntryFactory(character_sheet=sheet)
    RosterTenureFactory(player_data=player_data, roster_entry=roster_entry)
    return PersonaFactory(character_sheet=sheet)


class SetLookingForTableTests(TestCase):
    def test_setting_flag_stamps_timestamp(self):
        """set_looking_for_table(True) sets the flag and stamps the timestamp."""
        player_data = PlayerDataFactory()
        set_looking_for_table(player_data, looking=True)
        player_data.refresh_from_db()
        self.assertTrue(player_data.looking_for_table)
        self.assertIsNotNone(player_data.looking_for_table_set_at)

    def test_clearing_flag_nulls_timestamp(self):
        """set_looking_for_table(False) clears the flag and nulls the timestamp."""
        player_data = PlayerDataFactory()
        set_looking_for_table(player_data, looking=True)
        set_looking_for_table(player_data, looking=False)
        player_data.refresh_from_db()
        self.assertFalse(player_data.looking_for_table)
        self.assertIsNone(player_data.looking_for_table_set_at)


class JoinTableAutoClearTests(TestCase):
    def test_join_table_clears_looking_for_table_flag(self):
        """join_table() auto-clears the looking-for-table flag."""
        player_data = PlayerDataFactory()
        set_looking_for_table(player_data, looking=True)
        persona = _make_persona_with_player_data(player_data)
        table = GMTableFactory()

        join_table(table, persona)

        player_data.refresh_from_db()
        self.assertFalse(player_data.looking_for_table)

    def test_join_table_noop_when_flag_already_false(self):
        """join_table() does not error when the flag is already False."""
        player_data = PlayerDataFactory()
        persona = _make_persona_with_player_data(player_data)
        table = GMTableFactory()

        join_table(table, persona)  # should not raise

        player_data.refresh_from_db()
        self.assertFalse(player_data.looking_for_table)
