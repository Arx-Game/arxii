"""Telnet tidings command tests (#1450) — thin over public_feed_for."""

from unittest.mock import MagicMock

from django.test import TestCase

from commands.social.tidings import CmdTidings
from world.roster.factories import RosterEntryFactory
from world.secrets.factories import SecretFactory
from world.societies.factories import (
    LegendEntryFactory,
    SocietyFactory,
    SocietyReputationFactory,
)


class TidingsCommandTests(TestCase):
    def setUp(self) -> None:
        self.entry = RosterEntryFactory()
        self.persona = self.entry.character_sheet.primary_persona
        self.caller = self.entry.character_sheet.character
        self.caller.msg = MagicMock()
        self.society = SocietyFactory(name="The Compact")
        SocietyReputationFactory(persona=self.persona, society=self.society, value=300)

    def _run(self, args: str = "") -> str:
        cmd = CmdTidings()
        cmd.caller = self.caller
        cmd.args = args
        cmd.switches = []
        cmd.func()
        return "\n".join(str(c.args[0]) for c in self.caller.msg.call_args_list if c.args)

    def test_lists_a_deed_and_a_scandal_in_your_circles(self) -> None:
        deed = LegendEntryFactory(title="slew the wyrm")
        deed.societies_aware.add(self.society)
        scandal = SecretFactory(content="consorts with the abyss")
        scandal.societies_exposed.add(self.society)

        out = self._run()

        assert "slew the wyrm" in out
        assert "consorts with the abyss" in out

    def test_empty_when_nothing_circulating(self) -> None:
        assert "no tidings circulating" in self._run().lower()
