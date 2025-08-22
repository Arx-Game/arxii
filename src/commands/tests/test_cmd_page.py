"""Tests for the page command."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from commands.evennia_overrides.communication import CmdPage
from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.roster.factories import (
    PlayerDataFactory,
    RosterEntryFactory,
    RosterTenureFactory,
)


class CmdPageTests(TestCase):
    """Tests for the page command."""

    def setUp(self):
        self.caller = AccountFactory(username="Alice")
        self.caller.msg = MagicMock()

        self.target_account = AccountFactory(username="BobAcc")
        self.target_account.msg = MagicMock()
        player_data = PlayerDataFactory(account=self.target_account)
        self.character = CharacterFactory(db_key="Bob")
        self.character.msg = MagicMock()
        roster_entry = RosterEntryFactory(character=self.character)
        RosterTenureFactory(roster_entry=roster_entry, player_data=player_data)

    @patch("commands.evennia_overrides.communication.search.object_search")
    def test_page_routes_to_character(self, mock_search):
        """Character name should deliver the message to the target character."""

        mock_search.return_value = [self.character]

        cmd = CmdPage()
        cmd.caller = self.caller
        cmd.args = "Bob=hello"
        cmd.func()

        mock_search.assert_called_once_with("Bob", exact=True)
        self.character.msg.assert_called_once_with("Alice pages: hello")
        self.target_account.msg.assert_not_called()
        self.caller.msg.assert_any_call("You page Bob: hello")

    @patch("commands.evennia_overrides.communication.search.object_search")
    def test_page_requires_active_player(self, mock_search):
        """The command should error if the character has no active player."""

        mock_search.return_value = [self.character]
        # Remove all tenures to simulate no active player
        self.character.roster_entry.tenures.all().delete()

        cmd = CmdPage()
        cmd.caller = self.caller
        cmd.args = "Bob=hi"
        cmd.func()

        self.target_account.msg.assert_not_called()
        self.character.msg.assert_not_called()
        self.caller.msg.assert_called_with("Character 'Bob' has no active player.")

    @patch("commands.evennia_overrides.communication.search.object_search")
    def test_page_requires_rostered_character(self, mock_search):
        """The command should error if the character is not on the roster."""

        unrostered = CharacterFactory(db_key="NoRoster")
        mock_search.return_value = [unrostered]

        cmd = CmdPage()
        cmd.caller = self.caller
        cmd.args = "NoRoster=hey"
        cmd.func()

        self.caller.msg.assert_called_with("Character 'NoRoster' is not on the roster.")

    def test_page_exposes_usage_metadata(self):
        """CmdPage should expose usage information for the frontend."""

        cmd = CmdPage()
        payload = cmd.to_payload()
        descriptor = payload["descriptors"][0]
        self.assertEqual(descriptor["prompt"], "page character=message")
        self.assertEqual(
            descriptor["params_schema"],
            {"character": {"type": "string"}, "message": {"type": "string"}},
        )
