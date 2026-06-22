"""Telnet E2E for ritual performance (#1331).

One focused test: a player types ``ritual Rite of Imbuing`` and the CEREMONY
ritual runs through the full telnet path
(``CmdRitual.func()`` → ``resolve_action_args()`` → ``PerformRitualAction.run()``),
creating a ``PendingRitualEffect`` that the ``imbue`` finisher command will later
consume.

Note: Rite of Imbuing is CEREMONY-kind (not SERVICE). CmdRitual creates a
PendingRitualEffect; the full imbue step is covered by the 5-step journey E2E in
test_weave_imbue_pull_journey_e2e.py.
"""

from unittest.mock import MagicMock

from django.test import TestCase

from commands.ritual import CmdRitual
from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import (
    CharacterResonanceFactory,
    ImbuingRitualFactory,
    ResonanceFactory,
)
from world.magic.models import PendingRitualEffect


class RitualTelnetE2ETests(TestCase):
    """The Imbuing CEREMONY ritual creates a PendingRitualEffect via the telnet command."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory(db_key="ImbuingMage")
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.resonance = ResonanceFactory()
        cls.char_resonance = CharacterResonanceFactory(
            character_sheet=cls.sheet,
            resonance=cls.resonance,
            balance=20,
            lifetime_earned=20,
        )
        cls.ritual = ImbuingRitualFactory()

    def test_imbuing_ceremony_via_telnet_creates_pending_effect(self) -> None:
        self.character.msg = MagicMock()
        cmd = CmdRitual()
        cmd.caller = self.character
        cmd.args = "Rite of Imbuing"
        cmd.raw_string = "ritual Rite of Imbuing"

        cmd.func()

        self.assertTrue(
            PendingRitualEffect.objects.filter(
                character=self.sheet,
                ritual=self.ritual,
            ).exists(),
            "CmdRitual with Rite of Imbuing must create a PendingRitualEffect.",
        )
        self.character.msg.assert_called()
