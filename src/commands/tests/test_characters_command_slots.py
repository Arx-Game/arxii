"""Tests for the slot line on telnet's ``@characters`` and the retired stock mint (#3996)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from commands.account.character_switching import CmdCharacters
from commands.default_cmdsets import AccountCmdSet
from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import RosterEntryFactory, RosterFactory, RosterTenureFactory
from world.roster.models.choices import RosterType


def _make_cmd(account):
    cmd = CmdCharacters()
    cmd.account = account
    cmd.caller = account
    cmd.args = ""
    cmd.raw_string = "@characters"
    cmd.cmdname = "@characters"
    return cmd


@override_settings(CHARACTER_SLOTS_BASELINE=4)
class CmdCharactersSlotLineTests(TestCase):
    def setUp(self):
        self.account = AccountFactory()
        self.player_data = self.account.player_data
        entry = RosterEntryFactory(
            character_sheet=CharacterSheetFactory(character__db_key="Held"),
            roster=RosterFactory(roster_type=RosterType.ACTIVE),
        )
        RosterTenureFactory(roster_entry=entry, player_data=self.player_data)
        self.account.msg = MagicMock()

    def _sent(self):
        with (
            patch.object(type(self.account), "get_puppeted_characters", return_value=[]),
            patch.object(type(self.account), "get_available_sessions", return_value=[]),
        ):
            _make_cmd(self.account).func()
        return "\n".join(str(c.args[0]) for c in self.account.msg.call_args_list)

    def test_player_sees_the_slot_line(self):
        sent = self._sent()
        assert "Held" in sent
        assert "Slots: 1 of 4" in sent

    def test_staff_sees_no_slot_line(self):
        self.account.is_staff = True
        self.account.save()
        sent = self._sent()
        assert "Held" in sent
        assert "Slots:" not in sent


class StockCharacterMintRemovedTests(TestCase):
    def test_charcreate_and_chardelete_are_not_in_the_account_cmdset(self):
        cmdset = AccountCmdSet()
        cmdset.at_cmdset_creation()
        keys = {cmd.key for cmd in cmdset.commands}
        assert "charcreate" not in keys
        assert "chardelete" not in keys
        assert "@ic" in keys or "ic" in keys
