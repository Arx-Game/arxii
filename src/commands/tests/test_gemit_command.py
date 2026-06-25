"""Telnet gemit command tests (#1450) — thin over broadcast_gemit."""

from unittest.mock import MagicMock

from django.test import TestCase

from commands.gemit import CmdGemit
from evennia_extensions.factories import AccountFactory
from world.narrative.constants import GemitReach
from world.narrative.models import Gemit
from world.societies.factories import OrganizationFactory, SocietyFactory


class GemitCommandTests(TestCase):
    def setUp(self) -> None:
        self.account = AccountFactory(is_staff=True)
        self.caller = MagicMock()
        self.caller.msg = MagicMock()

    def _run(self, args: str = "", switches: list[str] | None = None) -> str:
        cmd = CmdGemit()
        cmd.caller = self.caller
        cmd.account = self.account
        cmd.args = args
        cmd.switches = switches or []
        cmd.func()
        return "\n".join(str(c.args[0]) for c in self.caller.msg.call_args_list if c.args)

    def test_game_wide_gemit_is_broadcast_verbatim(self) -> None:
        out = self._run("|rWar|n has come to the realm.")
        gemit = Gemit.objects.get()
        assert gemit.reach == GemitReach.GAME_WIDE
        assert gemit.body == "|rWar|n has come to the realm."
        assert "game-wide" in out.lower()

    def test_society_gemit_targets_the_named_society(self) -> None:
        society = SocietyFactory(name="The Compact")
        self._run("The Compact = The Compact stirs.", switches=["society"])
        gemit = Gemit.objects.get()
        assert gemit.reach == GemitReach.SPECIFIED
        assert list(gemit.reach_societies.all()) == [society]
        assert gemit.body == "The Compact stirs."

    def test_org_gemit_targets_the_named_organization(self) -> None:
        org = OrganizationFactory(name="The Wardens")
        self._run("The Wardens = Muster at dawn.", switches=["org"])
        gemit = Gemit.objects.get()
        assert gemit.reach == GemitReach.SPECIFIED
        assert list(gemit.reach_organizations.all()) == [org]

    def test_unknown_society_is_refused(self) -> None:
        out = self._run("Nowhere = Hello.", switches=["society"])
        assert "no society named" in out.lower()
        assert not Gemit.objects.exists()

    def test_scoped_gemit_requires_a_message(self) -> None:
        SocietyFactory(name="The Compact")
        out = self._run("The Compact", switches=["society"])
        assert "usage" in out.lower()
        assert not Gemit.objects.exists()
