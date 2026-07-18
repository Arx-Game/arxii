"""Tests for the petition telnet pointer (#2288)."""

from unittest.mock import MagicMock

from django.test import TestCase

from commands.account.staff_contact import CmdPetition
from evennia_extensions.factories import AccountFactory
from world.player_submissions.constants import SubmissionStatus
from world.player_submissions.factories import PetitionFactory


class CmdPetitionTests(TestCase):
    def setUp(self) -> None:
        self.account = AccountFactory(username="petitioncmd")
        self.caller = MagicMock()

    def _run(self, args: str = "") -> str:
        cmd = CmdPetition()
        cmd.account = self.account
        cmd.caller = self.caller
        cmd.args = args
        cmd.func()
        return self.caller.msg.call_args[0][0]

    def test_no_open_petition_points_to_web(self) -> None:
        self.assertIn("website", self._run())

    def test_open_petition_status_shown(self) -> None:
        petition = PetitionFactory(account=self.account)
        message = self._run("status")
        self.assertIn(petition.get_category_display(), message)

    def test_resolved_petition_not_reported_open(self) -> None:
        PetitionFactory(account=self.account, status=SubmissionStatus.REVIEWED)
        self.assertIn("no open petition", self._run())

    def test_unknown_subverb_rejected(self) -> None:
        self.assertIn("Unknown petition command", self._run("file something"))
