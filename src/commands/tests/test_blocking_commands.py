"""Telnet block/mute command tests (#1278) — thin wrappers over the services."""

from unittest.mock import MagicMock

from django.test import TestCase

from commands.social.blocking import CmdBlock, CmdBlockList, CmdMute, CmdUnmute
from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.roster.factories import (
    PlayerDataFactory,
    RosterEntryFactory,
    RosterTenureFactory,
)
from world.scenes.models import Block, Mute


class BlockingCommandTests(TestCase):
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

    def _run(self, cmd_class, args):
        cmd = cmd_class()
        cmd.caller = self.caller
        cmd.account = self.account
        cmd.args = args
        cmd.func()
        return cmd

    def test_block_requires_a_reason(self) -> None:
        self._run(CmdBlock, "Bob")
        assert not Block.objects.filter(owner__account=self.account).exists()
        self.caller.msg.assert_called()

    def test_block_creates_a_block(self) -> None:
        self._run(CmdBlock, "Bob=They were cruel")
        assert Block.objects.filter(
            owner__account=self.account,
            blocked_persona__character_sheet__character=self.target,
        ).exists()

    def test_mute_creates_an_ooc_only_mute(self) -> None:
        self._run(CmdMute, "Bob=ooc")
        mute = Mute.objects.get(owner__account=self.account)
        assert mute.mute_ooc is True
        assert mute.mute_ic is False

    def test_unmute_removes_the_mute(self) -> None:
        self._run(CmdMute, "Bob")
        self._run(CmdUnmute, "Bob")
        assert not Mute.objects.filter(owner__account=self.account).exists()

    def test_blocklist_runs_and_messages(self) -> None:
        self._run(CmdBlock, "Bob=reason")
        self.caller.msg.reset_mock()
        self._run(CmdBlockList, "")
        self.caller.msg.assert_called()
        sent = self.caller.msg.call_args[0][0]
        assert "Bob" in sent
