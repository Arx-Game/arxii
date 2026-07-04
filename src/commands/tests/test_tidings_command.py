"""Telnet tidings command tests (#1450) — thin over the tidings services."""

from unittest.mock import MagicMock

from django.test import TestCase, tag

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

    def test_unknown_argument_shows_usage(self) -> None:
        assert "usage" in self._run("gossip").lower()

    def test_local_without_a_hub_room_is_refused(self) -> None:
        # The caller has no location at all — the strictest no-hub case.
        self.caller.location = None
        assert "no notice board or crier" in self._run("local").lower()


@tag("postgres")  # Area.save() refreshes the areas_areaclosure materialized view
class TidingsLocalCommandTests(TestCase):
    """``tidings local`` — the civic-hub scope, gated on a board/crier in the room."""

    def setUp(self) -> None:
        from evennia_extensions.factories import RoomProfileFactory
        from world.areas.constants import AreaLevel
        from world.areas.factories import AreaFactory
        from world.room_features.models import RoomFeatureInstance
        from world.room_features.seeds import ensure_notice_board_kind, ensure_town_crier_kind

        self.entry = RosterEntryFactory()
        self.caller = self.entry.character_sheet.character
        self.caller.msg = MagicMock()
        self.crown = SocietyFactory(name="The Crown")
        kingdom = AreaFactory(level=AreaLevel.KINGDOM, dominant_society=self.crown)
        self.room_profile = RoomProfileFactory(area=kingdom)
        self.caller.location = self.room_profile.objectdb
        self.board_kind = ensure_notice_board_kind()
        self.crier_kind = ensure_town_crier_kind()
        self._instances = RoomFeatureInstance.objects

    def _run(self) -> str:
        self.caller.msg.reset_mock()
        cmd = CmdTidings()
        cmd.caller = self.caller
        cmd.args = "local"
        cmd.switches = []
        cmd.func()
        return "\n".join(str(c.args[0]) for c in self.caller.msg.call_args_list if c.args)

    def test_no_hub_feature_is_refused(self) -> None:
        assert "no notice board or crier" in self._run().lower()

    def test_board_lists_local_tidings_with_board_header(self) -> None:
        self._instances.create(room_profile=self.room_profile, feature_kind=self.board_kind)
        deed = LegendEntryFactory(title="crowned the tourney")
        deed.societies_aware.add(self.crown)

        out = self._run()

        assert "notice board" in out.lower()
        assert "crowned the tourney" in out

    def test_crier_uses_the_crier_header(self) -> None:
        self._instances.create(room_profile=self.room_profile, feature_kind=self.crier_kind)
        deed = LegendEntryFactory(title="crowned the tourney")
        deed.societies_aware.add(self.crown)

        assert "crier" in self._run().lower()

    def test_hub_with_quiet_locale_reports_quiet(self) -> None:
        self._instances.create(room_profile=self.room_profile, feature_kind=self.board_kind)
        assert "quiet" in self._run().lower()
