"""Telnet E2E: ``weave`` creates a Thread identically to the web path (#1337).

One focused test: a player types ``weave resonance=<name> trait=<id> name=<...>``
and a ``Thread`` is woven through the full telnet path
(``CmdWeaveThread.func()`` → ``resolve_action_args()`` → ``WeaveThreadAction.run()``
→ ``weave_thread``), exactly as the web viewset reaches the same action.

Sparse by design — the web side of the same action is covered by the weave
viewset/serializer tests; this proves the direct-viewset → Action telnet pattern.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from commands.weave import CmdWeaveThread
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import TargetKind
from world.magic.factories import (
    CharacterThreadWeavingUnlockFactory,
    ResonanceFactory,
    ThreadWeavingUnlockFactory,
)
from world.magic.models import Thread
from world.traits.factories import TraitFactory


class WeaveTelnetE2ETests(TestCase):
    """Weaving runs end-to-end from the telnet command."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory(name="Embers")
        cls.trait = TraitFactory()
        unlock = ThreadWeavingUnlockFactory(target_kind=TargetKind.TRAIT, unlock_trait=cls.trait)
        CharacterThreadWeavingUnlockFactory(character=cls.sheet, unlock=unlock, xp_spent=100)

    def test_weave_via_telnet_creates_thread(self) -> None:
        character = self.sheet.character
        character.msg = MagicMock()
        cmd = CmdWeaveThread()
        cmd.caller = character
        cmd.args = f"resonance=Embers trait={self.trait.pk} name=First"
        cmd.raw_string = f"weave {cmd.args}"

        cmd.func()

        thread = Thread.objects.get(owner=self.sheet, resonance=self.resonance)
        self.assertEqual(thread.name, "First")
        character.msg.assert_called()
