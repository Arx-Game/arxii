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
        self.caller.msg.reset_mock()  # so each call reads only this run's output, not accumulated
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

    def test_feed_follows_the_active_persona(self) -> None:
        """Switching the active face changes the tidings — scoping is persona-level, not char."""
        from world.scenes.constants import PersonaType
        from world.scenes.factories import PersonaFactory
        from world.scenes.services import set_active_persona

        deed_primary = LegendEntryFactory(title="deed of my true face")
        deed_primary.societies_aware.add(self.society)

        alt = PersonaFactory(
            character_sheet=self.entry.character_sheet, persona_type=PersonaType.ESTABLISHED
        )
        alt_society = SocietyFactory(name="The Hollow")
        SocietyReputationFactory(persona=alt, society=alt_society, value=200)
        deed_alt = LegendEntryFactory(title="deed of my other face")
        deed_alt.societies_aware.add(alt_society)

        out_primary = self._run()
        assert "deed of my true face" in out_primary
        assert "deed of my other face" not in out_primary

        set_active_persona(self.entry.character_sheet, alt)
        out_alt = self._run()
        assert "deed of my other face" in out_alt
        assert "deed of my true face" not in out_alt

    def test_masked_persona_sees_no_tidings(self) -> None:
        """A TEMPORARY mask holds no memberships, so a disguised character's feed is empty."""
        from world.scenes.constants import PersonaType
        from world.scenes.factories import PersonaFactory
        from world.scenes.services import set_active_persona

        deed = LegendEntryFactory(title="known to my true face")
        deed.societies_aware.add(self.society)

        mask = PersonaFactory(
            character_sheet=self.entry.character_sheet, persona_type=PersonaType.TEMPORARY
        )
        set_active_persona(self.entry.character_sheet, mask)

        assert "no tidings circulating" in self._run().lower()
