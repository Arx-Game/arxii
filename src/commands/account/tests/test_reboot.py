"""Tests for the staff ``@reboot`` command (#4001)."""

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from commands.account.reboot import CmdReboot
from commands.default_cmdsets import AccountCmdSet


class CmdRebootTests(SimpleTestCase):
    def _run(self) -> tuple[MagicMock, MagicMock]:
        cmd = CmdReboot()
        cmd.caller = MagicMock()
        cmd.caller.name = "Apostate"
        cmd.account = cmd.caller
        cmd.args = ""
        with patch("commands.account.reboot.request_reboot") as request:
            cmd.func()
        return cmd.caller, request

    def test_asks_for_a_reboot_in_the_callers_name(self) -> None:
        _caller, request = self._run()
        request.assert_called_once_with(requested_by="Apostate")

    def test_tells_the_caller_what_is_happening(self) -> None:
        caller, _request = self._run()
        message = caller.msg.call_args[0][0]
        self.assertIn("restart", message.lower())

    def test_does_nothing_for_a_caller_with_no_session(self) -> None:
        """Mirrors Evennia's own shutdown guard: only a connected staffer reboots."""
        cmd = CmdReboot()
        cmd.caller = MagicMock()
        cmd.caller.sessions.get.return_value = []
        cmd.account = cmd.caller
        cmd.args = ""
        with patch("commands.account.reboot.request_reboot") as request:
            cmd.func()
        request.assert_not_called()

    def test_is_developer_locked_and_distinct_from_shutdown(self) -> None:
        """`@shutdown` stays a real shutdown; this is its own verb, and never
        Evennia's `@restart`, which is an alias of `@reload` (Server only)."""
        self.assertEqual(CmdReboot.key, "@reboot")
        self.assertNotIn("@restart", CmdReboot.aliases)
        self.assertNotIn("@shutdown", CmdReboot.aliases)
        self.assertIn("perm(Developer)", CmdReboot.locks)

    def test_is_in_the_account_cmdset(self) -> None:
        cmdset = AccountCmdSet()
        cmdset.at_cmdset_creation()
        keys = {cmd.key for cmd in cmdset.commands}
        self.assertIn("@reboot", keys)
        self.assertIn("@shutdown", keys)
