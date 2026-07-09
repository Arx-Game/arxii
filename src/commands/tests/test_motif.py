"""Telnet E2E tests for CmdMotif — the ``motif`` style-binding namespace (#2030).

Drives ``CmdMotif`` end-to-end through the three motif style-binding verbs
(bindstyle / unbindstyle / list) over the shared ``dispatch_player_action``
seam, asserting DB state after each step and telnet feedback via
``caller.msg``. Mirrors ``integration_tests/pipeline/test_signature_telnet_e2e.py``'s
real-dispatch style (not mocked) since these cases assert actual row creation/removal.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase
from evennia.utils import idmapper

from commands.motif import CmdMotif
from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.items.factories import StyleFactory
from world.magic.factories import CharacterResonanceFactory, ResonanceFactory
from world.magic.models import MotifResonanceStyle

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(caller: object, args: str = "") -> CmdMotif:
    """Wire CmdMotif to *caller* and call func(). Returns the cmd instance."""
    cmd = CmdMotif()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"motif {args}".strip()
    cmd.cmdname = "motif"
    caller.msg = MagicMock()
    cmd.func()
    return cmd


class MotifTelnetE2ETest(TestCase):
    """bindstyle / unbindstyle / list through telnet CmdMotif."""

    def setUp(self) -> None:
        idmapper.models.flush_cache()

        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)

        self.resonance = ResonanceFactory(name="Ember")
        self.style = StyleFactory(name="Seductive")

        # The character has claimed the resonance (a binding prerequisite).
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=self.resonance)

    # ------------------------------------------------------------------
    # bindstyle
    # ------------------------------------------------------------------

    def test_bindstyle_happy_path_creates_row(self) -> None:
        """motif bindstyle <style>=<resonance> → MotifResonanceStyle row created."""
        _run(self.character, f"bindstyle {self.style.name}={self.resonance.name}")

        binding = MotifResonanceStyle.objects.filter(
            motif_resonance__motif__character=self.sheet, style=self.style
        ).first()
        self.assertIsNotNone(binding, "bind should create the MotifResonanceStyle row")
        self.assertEqual(binding.motif_resonance.resonance, self.resonance)

        self.character.msg.assert_called()
        msg = self.character.msg.call_args[0][0]
        self.assertIn(self.style.name, msg)
        self.assertIn(self.resonance.name, msg)

    def test_bindstyle_unknown_style_is_rejected_no_row(self) -> None:
        """motif bindstyle with an unknown style → error message, no row created."""
        _run(self.character, f"bindstyle Nonexistent={self.resonance.name}")

        self.assertFalse(MotifResonanceStyle.objects.exists())
        self.character.msg.assert_called()
        msg = self.character.msg.call_args_list[0][0][0]
        self.assertIn("no style called", msg.lower())

    def test_bindstyle_unclaimed_resonance_surfaces_service_message(self) -> None:
        """motif bindstyle with an unclaimed resonance → service user_message surfaced."""
        unclaimed = ResonanceFactory(name="Void")

        _run(self.character, f"bindstyle {self.style.name}={unclaimed.name}")

        self.assertFalse(MotifResonanceStyle.objects.exists())
        self.character.msg.assert_called()
        msg = self.character.msg.call_args[0][0]
        self.assertIn("have not claimed", msg.lower())

    def test_bindstyle_missing_resonance_side_is_rejected(self) -> None:
        """motif bindstyle without '=<resonance>' → usage error, no dispatch."""
        _run(self.character, f"bindstyle {self.style.name}")

        self.assertFalse(MotifResonanceStyle.objects.exists())
        self.character.msg.assert_called()
        msg = self.character.msg.call_args_list[0][0][0]
        self.assertIn("usage", msg.lower())

    # ------------------------------------------------------------------
    # unbindstyle
    # ------------------------------------------------------------------

    def test_unbindstyle_removes_row(self) -> None:
        """motif unbindstyle <style> → binding removed."""
        _run(self.character, f"bindstyle {self.style.name}={self.resonance.name}")
        self.assertTrue(MotifResonanceStyle.objects.exists())

        _run(self.character, f"unbindstyle {self.style.name}")

        self.assertFalse(MotifResonanceStyle.objects.exists())
        self.character.msg.assert_called()
        msg = self.character.msg.call_args[0][0]
        self.assertIn("no longer bound", msg.lower())

    def test_unbindstyle_unknown_style_is_rejected(self) -> None:
        """motif unbindstyle with an unknown style → error message."""
        _run(self.character, "unbindstyle Nonexistent")

        self.character.msg.assert_called()
        msg = self.character.msg.call_args_list[0][0][0]
        self.assertIn("no style called", msg.lower())

    def test_unbindstyle_not_bound_surfaces_service_message(self) -> None:
        """motif unbindstyle on a style that exists but isn't bound → service message."""
        _run(self.character, f"unbindstyle {self.style.name}")

        self.character.msg.assert_called()
        msg = self.character.msg.call_args[0][0]
        self.assertIn("not bound", msg.lower())

    # ------------------------------------------------------------------
    # list
    # ------------------------------------------------------------------

    def test_bare_motif_lists_bindings(self) -> None:
        """bare 'motif' → shows bound styles."""
        _run(self.character, f"bindstyle {self.style.name}={self.resonance.name}")

        _run(self.character, "")

        self.character.msg.assert_called()
        msg = self.character.msg.call_args[0][0]
        self.assertIn(self.style.name, msg)
        self.assertIn(self.resonance.name, msg)

    def test_motif_list_subverb_lists_bindings(self) -> None:
        """'motif list' → same as bare motif."""
        _run(self.character, f"bindstyle {self.style.name}={self.resonance.name}")

        _run(self.character, "list")

        self.character.msg.assert_called()
        msg = self.character.msg.call_args[0][0]
        self.assertIn(self.style.name, msg)

    def test_bare_motif_no_bindings_shows_hint(self) -> None:
        """bare 'motif' with no bindings → placeholder hint, no error."""
        _run(self.character, "")

        self.character.msg.assert_called()
        msg = self.character.msg.call_args[0][0]
        self.assertIn("no styles bound", msg.lower())
