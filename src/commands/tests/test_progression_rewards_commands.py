"""Parse/error-path tests for the progression-reward telnet commands (#1348).

These tests exercise argument parsing and early-exit error messages only.
Business logic lives in the actions and is tested there.
"""

from unittest.mock import MagicMock

from django.test import TestCase

from commands.progression_rewards import CmdKudos, CmdPathIntent, CmdRandomScene, CmdVote
from world.character_sheets.factories import CharacterSheetFactory


def _run(cmd_cls, caller, args=""):
    cmd = cmd_cls()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"{cmd_cls.key} {args}".strip()
    caller.msg = MagicMock()
    cmd.func()
    return [str(c.args[0]) for c in caller.msg.call_args_list if c.args]


class CommandParseTests(TestCase):
    def setUp(self) -> None:
        self.character = CharacterSheetFactory().character

    def test_kudos_claim_bad_args_messages_usage(self) -> None:
        msgs = _run(CmdKudos, self.character, "claim notanumber")
        self.assertTrue(any("usage" in m.lower() or "number" in m.lower() for m in msgs))

    def test_vote_bad_target_type_messages(self) -> None:
        msgs = _run(CmdVote, self.character, "banana 5")
        self.assertTrue(any("target" in m.lower() for m in msgs))

    def test_randomscene_unknown_subcommand(self) -> None:
        msgs = _run(CmdRandomScene, self.character, "frobnicate")
        self.assertTrue(msgs)

    def test_pathintent_clear_runs(self) -> None:
        # no active character account → action returns failure, but command must not crash
        msgs = _run(CmdPathIntent, self.character, "clear")
        self.assertTrue(msgs)
