"""Tests for the page command."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from commands.evennia_overrides.communication import CmdPage
from evennia_extensions.factories import AccountFactory, CharacterFactory
from evennia_extensions.models import PlayerAllowList
from world.roster.factories import (
    PlayerDataFactory,
    RosterEntryFactory,
    RosterTenureFactory,
    TenureDisplaySettingsFactory,
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
        roster_entry = RosterEntryFactory(character_sheet__character=self.character)
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
        self.character.sheet_data.roster_entry.tenures.all().delete()

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

    @patch("commands.evennia_overrides.communication.search.object_search")
    def test_hidden_target_is_unreachable_to_stranger(self, mock_search):
        """A quiet-mode target gets the same 'not online' response as if offline (#1463)."""
        mock_search.return_value = [self.character]
        TenureDisplaySettingsFactory(
            tenure=self.character.sheet_data.roster_entry.current_tenure, appear_offline=True
        )

        cmd = CmdPage()
        cmd.caller = self.caller
        cmd.args = "Bob=hi"
        cmd.func()

        self.character.msg.assert_not_called()
        self.caller.msg.assert_called_with("Character 'Bob' is not online.")

    @patch("commands.evennia_overrides.communication.search.object_search")
    def test_hidden_target_is_reachable_to_allowlisted_sender(self, mock_search):
        """The target's allowlist exempts a sender from quiet mode (#1463)."""
        mock_search.return_value = [self.character]
        TenureDisplaySettingsFactory(
            tenure=self.character.sheet_data.roster_entry.current_tenure, appear_offline=True
        )
        PlayerAllowList.objects.create(
            owner=self.target_account.player_data,
            allowed_player=PlayerDataFactory(account=self.caller),
        )

        cmd = CmdPage()
        cmd.caller = self.caller
        cmd.args = "Bob=hi"
        cmd.func()

        self.character.msg.assert_called_once_with("Alice pages: hi")

    @patch("commands.evennia_overrides.communication.search.object_search")
    def test_hidden_sender_cannot_page_non_allowlisted_target(self, mock_search):
        """A hidden sender can only page their own allowlist, never stranding a friend (#1463)."""
        mock_search.return_value = [self.character]
        sender_char = CharacterFactory(db_key="Alu")
        sender_char.msg = MagicMock()
        sender_entry = RosterEntryFactory(character_sheet__character=sender_char)
        sender_tenure = RosterTenureFactory(
            roster_entry=sender_entry, player_data=PlayerDataFactory(account=self.caller)
        )
        TenureDisplaySettingsFactory(tenure=sender_tenure, appear_offline=True)

        cmd = CmdPage()
        cmd.caller = self.caller
        cmd.session = MagicMock(puppet=sender_char)
        cmd.args = "Bob=hi"
        cmd.func()

        self.character.msg.assert_not_called()
        assert "hidden" in self.caller.msg.call_args[0][0].lower()

    def test_page_exposes_usage_metadata(self):
        """CmdPage should expose usage information for the frontend."""

        cmd = CmdPage()
        payload = cmd.to_payload()
        descriptor = payload["descriptors"][0]
        assert descriptor["prompt"] == "page character=message"
        assert descriptor["params_schema"] == {
            "character": {
                "type": "string",
                "widget": "character-search",
                "options_endpoint": "/api/characters/online/",
            },
            "message": {"type": "string"},
        }
