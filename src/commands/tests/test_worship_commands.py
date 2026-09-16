"""Telnet faces of prayer and the vision (#3779): parsing only."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.types import ActionResult
from commands.worship import CmdPray, CmdVision


def _messages(caller: MagicMock) -> list[str]:
    return [str(c.args[0]) for c in caller.msg.call_args_list if c.args]


class CmdPrayTests(TestCase):
    def setUp(self) -> None:
        self.caller = MagicMock()
        self.cmd = CmdPray()
        self.cmd.caller = self.caller
        self.cmd.switches = []

    def test_missing_words_shows_usage(self) -> None:
        self.cmd.args = "The Shepherd"
        self.cmd.func()
        self.assertTrue(any("Usage" in m for m in _messages(self.caller)))

    @patch("actions.definitions.worship.PrayAction.run")
    def test_being_and_words_split_on_the_first_equals(self, run) -> None:
        run.return_value = ActionResult(success=True, message="You pray.")
        self.cmd.args = "The Shepherd = keep us = whole"
        self.cmd.func()
        run.assert_called_once_with(
            actor=self.caller, being_name="The Shepherd", text="keep us = whole"
        )


class CmdVisionTests(TestCase):
    def setUp(self) -> None:
        self.caller = MagicMock()
        self.cmd = CmdVision()
        self.cmd.caller = self.caller
        self.cmd.account = MagicMock()

    @patch("actions.definitions.worship.SendVisionAction.run")
    def test_reveal_switch_and_prayer_id_reach_the_action(self, run) -> None:
        run.return_value = ActionResult(success=True, message="sent")
        self.cmd.switches = ["reveal", "prayer"]
        self.cmd.args = "12 Alaric/The Shepherd=A door opens."
        self.cmd.func()
        run.assert_called_once_with(
            actor=self.caller,
            account=self.cmd.account,
            recipient_name="Alaric",
            being_name="The Shepherd",
            body="A door opens.",
            reveal_source=True,
            prayer=12,
        )

    def test_missing_being_shows_usage(self) -> None:
        self.cmd.switches = []
        self.cmd.args = "Alaric=A door opens."
        self.cmd.func()
        self.assertTrue(any("Usage" in m for m in _messages(self.caller)))
