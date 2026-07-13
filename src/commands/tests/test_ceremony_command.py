"""Tests for the ``ceremony`` telnet command family (#2289)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.types import ActionResult
from commands.ceremonies import CmdCeremony


def _make_cmd(caller, args: str, switches: list[str] | None = None) -> CmdCeremony:
    cmd = CmdCeremony()
    cmd.caller = caller
    cmd.args = args
    cmd.switches = switches or []
    cmd.raw_string = f"ceremony {args}".strip()
    return cmd


def _messages(caller: MagicMock) -> list[str]:
    return [str(c.args[0]) for c in caller.msg.call_args_list if c.args]


class CmdCeremonyRoutingTests(TestCase):
    def setUp(self) -> None:
        self.caller = MagicMock()
        self.caller.msg = MagicMock()

    def _run(self, args: str, switches: list[str] | None = None) -> list[str]:
        cmd = _make_cmd(self.caller, args, switches)
        cmd.func()
        return _messages(self.caller)

    def test_unknown_subverb_shows_usage(self) -> None:
        messages = self._run("banquet")
        self.assertTrue(any("Usage" in m for m in messages))

    @patch("actions.definitions.ceremonies.OpenCeremonyAction.run")
    def test_switch_form_opens_funeral_with_names_and_being(self, run) -> None:
        run.return_value = ActionResult(success=True, message="opened")
        self._run("Alaric, Beatrice=The Shepherd", switches=["funeral"])
        run.assert_called_once_with(
            actor=self.caller,
            type_key="funeral",
            honoree_names=["Alaric", "Beatrice"],
            being_name="The Shepherd",
        )

    @patch("actions.definitions.ceremonies.OpenCeremonyAction.run")
    def test_space_form_routes_too(self, run) -> None:
        run.return_value = ActionResult(success=True, message="opened")
        self._run("funeral Alaric")
        run.assert_called_once_with(
            actor=self.caller,
            type_key="funeral",
            honoree_names=["Alaric"],
            being_name=None,
        )

    @patch("actions.definitions.ceremonies.CeremonyOfferingAction.run")
    def test_offering_splits_item_names(self, run) -> None:
        run.return_value = ActionResult(success=True, message="consumed")
        self._run("golden chalice, silver ring", switches=["offering"])
        run.assert_called_once_with(actor=self.caller, item_names=["golden chalice", "silver ring"])

    @patch("actions.definitions.ceremonies.CeremonySpeechAction.run")
    def test_speech_with_target_honoree(self, run) -> None:
        run.return_value = ActionResult(success=True, message="recognized")
        self._run("Cedric=Alaric", switches=["speech"])
        run.assert_called_once_with(actor=self.caller, speaker_name="Cedric", honoree_name="Alaric")

    @patch("actions.definitions.ceremonies.FinishCeremonyAction.run")
    def test_finish_routes(self, run) -> None:
        run.return_value = ActionResult(success=True, message="concluded")
        self._run("finish")
        run.assert_called_once_with(actor=self.caller)

    @patch("actions.definitions.ceremonies.AbandonCeremonyAction.run")
    def test_abandon_routes(self, run) -> None:
        run.return_value = ActionResult(success=True, message="left unfinished")
        self._run("abandon")
        run.assert_called_once_with(actor=self.caller)

    @patch("actions.definitions.ceremonies._open_ceremony_here", return_value=None)
    def test_bare_ceremony_shows_none_underway(self, lookup) -> None:
        messages = self._run("")
        lookup.assert_called_once()
        self.assertTrue(any("No ceremony is underway" in m for m in messages))
