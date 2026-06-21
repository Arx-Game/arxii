"""Telnet E2E for ritual performance (#1331).

One focused test: a player types ``ritual Rite of Imbuing thread=<id>`` and the
Imbuing SERVICE ritual runs through the full telnet path
(``CmdRitual.func()`` → ``resolve_action_args()`` → ``PerformRitualAction.run()``
→ ``spend_resonance_for_imbuing``), advancing the thread and debiting resonance.

Sparse by design — the user replaces these with user-journey integration tests.
The web side of the same action is covered by ``RitualPerformViewTests``.
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
    ThreadFactory,
)
from world.traits.factories import TraitFactory


class RitualTelnetE2ETests(TestCase):
    """The Imbuing ritual runs end-to-end from the telnet command."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory(db_key="ImbuingMage")
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.resonance = ResonanceFactory()
        cls.thread = ThreadFactory(
            owner=cls.sheet,
            resonance=cls.resonance,
            target_trait=TraitFactory(),
            level=2,
            _trait_value=9,  # anchor cap 9 — headroom under level 10
        )
        cls.char_resonance = CharacterResonanceFactory(
            character_sheet=cls.sheet,
            resonance=cls.resonance,
            balance=20,
            lifetime_earned=20,
        )
        cls.ritual = ImbuingRitualFactory()

    def test_imbuing_via_telnet_advances_thread_and_debits_resonance(self) -> None:
        self.character.msg = MagicMock()
        cmd = CmdRitual()
        cmd.caller = self.character
        cmd.args = f"Rite of Imbuing thread={self.thread.pk} amount=5"
        cmd.raw_string = cmd.args

        cmd.func()

        self.thread.refresh_from_db()
        self.char_resonance.refresh_from_db()
        self.assertGreater(self.thread.developed_points + self.thread.level, 2)
        self.assertEqual(self.char_resonance.balance, 15)
        self.character.msg.assert_called()
