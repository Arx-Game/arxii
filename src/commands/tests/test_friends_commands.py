"""Telnet friends commands (#1727)."""

from unittest.mock import MagicMock

from django.test import TestCase

from commands.social.friends import CmdFriend, CmdFriends, CmdUnfriend
from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.models import Friendship


class FriendsCommandTests(TestCase):
    def _played(self, character, account=None):
        account = account or AccountFactory()
        player_data = PlayerDataFactory(account=account)
        entry = RosterEntryFactory(character_sheet__character=character)
        RosterTenureFactory(roster_entry=entry, player_data=player_data)
        return account

    def setUp(self) -> None:
        self.caller = CharacterFactory(db_key="Alice")
        self.caller.msg = MagicMock()
        self.account = self._played(self.caller)
        self.account.msg = MagicMock()
        self.target = CharacterFactory(db_key="Bob")
        self._played(self.target)
        self.caller.search = MagicMock(return_value=self.target)

    def _run(self, cmd_class, args, switches=None):
        cmd = cmd_class()
        cmd.caller = self.caller
        cmd.account = self.account
        cmd.args = args
        cmd.switches = switches or []
        cmd.func()
        return cmd

    def test_friend_creates_a_friendship_from_this_character(self) -> None:
        self._run(CmdFriend, "Bob")
        self.assertTrue(
            Friendship.objects.filter(
                friend_tenure__roster_entry__character_sheet__character=self.target
            ).exists()
        )
        self.caller.msg.assert_called()

    def test_friend_requires_a_target(self) -> None:
        self._run(CmdFriend, "")
        self.assertFalse(Friendship.objects.exists())

    def test_unfriend_removes_it(self) -> None:
        self._run(CmdFriend, "Bob")
        self._run(CmdUnfriend, "Bob")
        self.assertFalse(Friendship.objects.exists())

    def test_friend_all_fans_out(self) -> None:
        self._run(CmdFriend, "Bob", switches=["all"])
        self.assertTrue(Friendship.objects.exists())

    def test_friends_list_shows_the_friend(self) -> None:
        self._run(CmdFriend, "Bob")
        self.caller.msg.reset_mock()
        self._run(CmdFriends, "")
        self.caller.msg.assert_called()
        self.assertIn("Bob", self.caller.msg.call_args[0][0])
