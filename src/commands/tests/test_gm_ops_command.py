"""Telnet tests for GM ops commands (#2004): ``story surrender``, ``gm dashboard``, ``gm idle``."""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from commands.gm_ops import CmdGMDashboard, CmdGMIdle
from commands.story import CmdStory
from evennia_extensions.factories import AccountFactory
from world.gm.factories import GMProfileFactory, GMTableFactory
from world.stories.factories import StoryFactory


def _make_story_cmd(caller, args: str) -> CmdStory:
    cmd = CmdStory()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"story {args}".strip()
    return cmd


def _make_dashboard_cmd(caller, args: str) -> CmdGMDashboard:
    cmd = CmdGMDashboard()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"gm {args}".strip()
    return cmd


def _make_idle_cmd(caller, args: str) -> CmdGMIdle:
    cmd = CmdGMIdle()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = "gmidle"
    return cmd


def _messages(caller: MagicMock) -> list[str]:
    return [str(c.args[0]) for c in caller.msg.call_args_list if c.args]


class StorySurrenderCommandTests(TestCase):
    def setUp(self) -> None:
        self.owner = AccountFactory()
        self.gm_profile = GMProfileFactory(account=self.owner)
        self.table = GMTableFactory(gm=self.gm_profile)
        self.story = StoryFactory(primary_table=self.table, owners=[self.owner])
        self.caller = MagicMock()
        self.caller.msg = MagicMock()
        self.caller.account = self.owner

    def _run(self, args: str) -> list[str]:
        cmd = _make_story_cmd(self.caller, args)
        cmd.func()
        return _messages(self.caller)

    def test_surrender_clears_primary_table(self) -> None:
        self._run(f"surrender {self.story.pk}")
        self.story.refresh_from_db()
        self.assertIsNone(self.story.primary_table)

    def test_non_owner_cannot_surrender(self) -> None:
        non_owner = AccountFactory()
        self.caller.account = non_owner
        self._run(f"surrender {self.story.pk}")
        self.story.refresh_from_db()
        self.assertIsNotNone(self.story.primary_table)


class GMDashboardCommandTests(TestCase):
    def setUp(self) -> None:
        self.gm_account = AccountFactory()
        self.gm_profile = GMProfileFactory(account=self.gm_account)
        self.table = GMTableFactory(gm=self.gm_profile)
        self.caller = MagicMock()
        self.caller.msg = MagicMock()
        self.caller.account = self.gm_account

    def _run(self, args: str) -> list[str]:
        cmd = _make_dashboard_cmd(self.caller, args)
        cmd.func()
        return _messages(self.caller)

    def test_dashboard_shows_table(self) -> None:
        messages = self._run("dashboard")
        joined = " ".join(messages)
        self.assertIn("GM Dashboard", joined)
        self.assertIn(self.table.name, joined)

    def test_non_gm_rejected(self) -> None:
        non_gm = AccountFactory()
        self.caller.account = non_gm
        messages = self._run("dashboard")
        self.assertTrue(any("GM profile" in m for m in messages))


class GMIdleCommandTests(TestCase):
    def setUp(self) -> None:
        self.staff = AccountFactory(is_staff=True)
        self.caller = MagicMock()
        self.caller.msg = MagicMock()
        self.caller.account = self.staff

    def _run(self, args: str) -> list[str]:
        cmd = _make_idle_cmd(self.caller, args)
        cmd.func()
        return _messages(self.caller)

    def test_no_idle_tables(self) -> None:
        messages = self._run("")
        self.assertTrue(any("no idle" in m.lower() for m in messages))

    def test_shows_idle_table(self) -> None:
        gm = GMProfileFactory()  # last_active_at is None → idle
        table = GMTableFactory(gm=gm)
        messages = self._run("")
        self.assertTrue(any(table.name in m for m in messages))
