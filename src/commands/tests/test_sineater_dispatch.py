"""Smoke tests for CmdSineater dispatch — verifies argument routing."""

from unittest.mock import MagicMock

from django.test import TestCase

from commands.social.soul_tether import CmdSineater


class SineaterDispatchTests(TestCase):
    def _run(self, args):
        cmd = CmdSineater()
        cmd.caller = MagicMock()
        cmd.caller.search.return_value = None
        cmd.args = args
        cmd.func()
        return cmd

    def test_unknown_subcommand_sends_usage(self):
        cmd = self._run("unknown")
        cmd.caller.msg.assert_called()
        assert "sineater" in cmd.caller.msg.call_args[0][0].lower()

    def test_consume_search_miss_sends_error(self):
        cmd = self._run("consume Nobody")
        cmd.caller.msg.assert_called()
        msg = cmd.caller.msg.call_args[0][0].lower()
        assert "could not find" in msg

    def test_pleas_no_sheet_sends_error(self):
        cmd = CmdSineater()
        cmd.caller = MagicMock()
        # Simulate "no sheet": the command reads the character_sheet property (audit).
        type(cmd.caller).character_sheet = None
        cmd.args = "pleas"
        cmd.caller.search.return_value = None
        cmd.func()
        cmd.caller.msg.assert_called()

    def test_rescue_no_args_sends_usage(self):
        cmd = CmdSineater()
        cmd.caller = MagicMock()
        cmd.caller.search.return_value = None
        cmd.args = "rescue"
        cmd.func()
        msg = cmd.caller.msg.call_args[0][0].lower()
        assert "rescue" in msg

    def test_cmdset_contains_both_commands(self):
        """CmdTether and CmdSineater are registered in CharacterCmdSet."""
        from commands.default_cmdsets import CharacterCmdSet

        cmdset = CharacterCmdSet()
        cmdset.at_cmdset_creation()
        keys = {cmd.key for cmd in cmdset.commands}
        assert "tether" in keys, "CmdTether not registered"
        assert "sineater" in keys, "CmdSineater not registered"
