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
from world.scenes.models import Block, BlockContactFlag


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


class CmdPageAccountBlockTests(TestCase):
    """#2996 Decision 2 — an account-level block upgrades pages to delivered-suppressed.

    The sender's own surface (their own ``caller.msg`` response, plus the pre-existing
    ``BlockContactFlag`` staff signal) is byte-identical write-then-filter; only the
    recipient's ``character.msg`` delivery is skipped.
    """

    def setUp(self):
        self.sender_account = AccountFactory(username="Sender")
        self.sender_char = CharacterFactory(db_key="Sender")
        sender_entry = RosterEntryFactory(character_sheet__character=self.sender_char)
        self.sender_player = PlayerDataFactory(account=self.sender_account)
        RosterTenureFactory(roster_entry=sender_entry, player_data=self.sender_player)
        self.sender_char.msg = MagicMock()

        self.receiver_account = AccountFactory(username="Receiver")
        self.receiver_account.msg = MagicMock()
        self.receiver_player = PlayerDataFactory(account=self.receiver_account)
        self.receiver_char = CharacterFactory(db_key="Receiver")
        self.receiver_char.msg = MagicMock()
        receiver_entry = RosterEntryFactory(character_sheet__character=self.receiver_char)
        RosterTenureFactory(roster_entry=receiver_entry, player_data=self.receiver_player)

    def _page(self):
        with patch(
            "commands.evennia_overrides.communication.search.object_search",
            return_value=[self.receiver_char],
        ):
            cmd = CmdPage()
            cmd.caller = self.sender_account
            cmd.caller.msg = MagicMock()
            cmd.session = MagicMock(puppet=self.sender_char)
            cmd.args = f"{self.receiver_char.db_key}=hello there"
            cmd.func()
        return cmd

    def test_blocked_pair_page_is_not_delivered(self):
        Block.objects.create(
            owner=self.receiver_player, blocked_player=self.sender_player, account_level=True
        )
        self._page()
        self.receiver_char.msg.assert_not_called()

    def test_blocked_pair_senders_own_surface_is_unchanged(self):
        """Write-then-filter: the sender's own response is identical to an unblocked send."""
        Block.objects.create(
            owner=self.receiver_player, blocked_player=self.sender_player, account_level=True
        )
        cmd = self._page()
        cmd.caller.msg.assert_called_once_with(f"You page {self.receiver_char.key}: hello there")

    def test_blocked_pair_still_flags_the_contact_attempt_for_staff(self):
        """The existing staff contact-flagging keeps firing under delivery suppression."""
        Block.objects.create(
            owner=self.receiver_player, blocked_player=self.sender_player, account_level=True
        )
        self._page()
        assert BlockContactFlag.objects.filter(
            blocked_account_id=self.sender_account.pk,
            blocker_account_id=self.receiver_account.pk,
        ).exists()

    def test_unblocked_pair_page_is_delivered_normally(self):
        self._page()
        self.receiver_char.msg.assert_called_once_with("Sender pages: hello there")
